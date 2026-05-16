#!/usr/bin/env python3
"""
Live scraping diagnostic — tests each company individually, reports pass/fail.

Usage:
    python scripts/check_scrapers.py                      # all enabled companies
    python scripts/check_scrapers.py --ats greenhouse     # one ATS type
    python scripts/check_scrapers.py --company anthropic  # one company
    python scripts/check_scrapers.py --include-disabled   # include disabled companies
    python scripts/check_scrapers.py --timeout 60         # per-company timeout (default 45s)
    python scripts/check_scrapers.py --ats greenhouse --fresh  # ignore cached results

Results are saved incrementally to scripts/scraping_status.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make sure project root is on sys.path when run as a script
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.amazon import AmazonScraper
from src.scrapers.google import GoogleScraper
from src.scrapers.apple import AppleScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.microsoft import MicrosoftScraper
from src.scrapers.workable import WorkableScraper
from src.scrapers.rippling import RipplingScraper
from src.scrapers.smartrecruiters import SmartRecruitersScraper
from src.scrapers.serp_fallback import SerpFallbackScraper
from src.scrapers.avature import AvatureScraper
from src.scrapers.oracle_cloud import OracleCloudScraper

STATUS_FILE = Path(__file__).parent / "scraping_status.json"
COMPANIES_FILE = _ROOT / "data" / "companies.json"

# Per-ATS default timeouts (seconds) — heavier scrapers get more time
_ATS_TIMEOUTS: dict[str, int] = {
    "workday": 90,   # 3-tier fallback chain
    "google": 60,    # Playwright
    "apple": 60,     # Playwright fallback
    "serp": 60,      # 3 pages × 10s rate limit
    "linkedin": 60,
    "oracle_cloud": 60,  # paginated GET
}

SCRAPER_MAP = {
    "greenhouse":     GreenhouseScraper,
    "lever":          LeverScraper,
    "workday":        WorkdayScraper,
    "amazon":         AmazonScraper,
    "google":         GoogleScraper,
    "apple":          AppleScraper,
    "ashby":          AshbyScraper,
    "microsoft":      MicrosoftScraper,
    "workable":       WorkableScraper,
    "rippling":       RipplingScraper,
    "smartrecruiters": SmartRecruitersScraper,
    "serp":           SerpFallbackScraper,
    "avature":        AvatureScraper,
    "oracle_cloud":   OracleCloudScraper,
}


async def test_company(company: dict, default_timeout: int = 45) -> dict:
    ats_type = company["ats_type"]
    scraper_cls = SCRAPER_MAP.get(ats_type)
    base_result = {
        "company": company["name"],
        "slug": company["slug"],
        "ats_type": ats_type,
        "enabled": company.get("enabled", True),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if scraper_cls is None:
        return {**base_result, "jobs": 0, "status": "fail",
                "error": f"no scraper registered for ats_type={ats_type!r}"}

    timeout = _ATS_TIMEOUTS.get(ats_type, default_timeout)

    try:
        async with scraper_cls() as scraper:
            jobs = await asyncio.wait_for(scraper.fetch_jobs(company, 0), timeout=timeout)
        count = len(jobs) if jobs else 0
        if count > 0:
            return {**base_result, "jobs": count, "status": "pass", "error": None}
        else:
            return {**base_result, "jobs": 0, "status": "fail", "error": "0 jobs returned"}
    except asyncio.TimeoutError:
        return {**base_result, "jobs": 0, "status": "fail",
                "error": f"timeout after {timeout}s"}
    except Exception as exc:
        return {**base_result, "jobs": 0, "status": "fail", "error": str(exc)[:200]}


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Live scraping diagnostic for all companies")
    parser.add_argument("--ats", help="Filter by ATS type (e.g. greenhouse)")
    parser.add_argument("--company", help="Filter by company slug (e.g. anthropic)")
    parser.add_argument("--include-disabled", action="store_true",
                        help="Also test disabled companies")
    parser.add_argument("--timeout", type=int, default=45,
                        help="Default per-company timeout in seconds (default: 45)")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore cached results and re-test all matching companies")
    args = parser.parse_args(argv)

    with open(COMPANIES_FILE) as f:
        all_companies: list[dict] = json.load(f)

    # Apply filters
    companies = all_companies
    if not args.include_disabled:
        # Support both "disabled: true" (new) and "enabled: false" (legacy)
        companies = [
            c for c in companies
            if not c.get("disabled", False) and c.get("enabled", True)
        ]
    if args.ats:
        companies = [c for c in companies if c["ats_type"] == args.ats]
    if args.company:
        companies = [c for c in companies if c["slug"] == args.company]

    # Load existing status
    status: dict[str, dict] = {}
    if STATUS_FILE.exists():
        with open(STATUS_FILE) as f:
            status = json.load(f)

    # Skip already-checked companies unless --fresh
    if not args.fresh:
        to_test = [c for c in companies if c["slug"] not in status]
        skipped = len(companies) - len(to_test)
        if skipped:
            print(f"  (skipping {skipped} already-checked; use --fresh to re-test)")
    else:
        to_test = companies

    print(f"Testing {len(to_test)} companies"
          + (f" (+ {len(companies)-len(to_test)} cached)" if not args.fresh else "")
          + " ...")
    print()

    results_this_run: list[dict] = []

    for i, company in enumerate(to_test, 1):
        label = f"{company['name']}"
        print(f"  [{i:3d}/{len(to_test)}] {label:35s} [{company['ats_type']:15s}]  ", end="", flush=True)
        t0 = time.monotonic()
        result = await test_company(company, default_timeout=args.timeout)
        elapsed = time.monotonic() - t0

        status[company["slug"]] = result
        results_this_run.append(result)

        # Persist incrementally so we can Ctrl-C and resume
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)

        if result["status"] == "pass":
            mark = "PASS"
            detail = f"{result['jobs']} jobs"
        else:
            mark = "FAIL"
            detail = (result.get("error") or "")[:80]

        print(f"{mark:4s}  {detail}  ({elapsed:.1f}s)")

    # ── Summary ─────────────────────────────────────────────────────────
    # Include cached results for the summary when running full-set queries
    summary_slugs = {c["slug"] for c in companies}
    all_relevant = {k: v for k, v in status.items() if k in summary_slugs}

    passed  = [r for r in all_relevant.values() if r["status"] == "pass"]
    failed  = [r for r in all_relevant.values() if r["status"] == "fail"]
    blocked = [r for r in all_relevant.values() if r["status"] == "blocked"]

    print()
    print("=" * 72)
    print(f"SUMMARY  pass={len(passed)}  fail={len(failed)}  blocked={len(blocked)}"
          f"  total={len(all_relevant)}")
    print("=" * 72)

    if failed:
        print("\nFAILED:")
        for r in sorted(failed, key=lambda x: x["ats_type"]):
            enabled_tag = "" if r.get("enabled", True) else " [disabled]"
            err = (r.get("error") or "")[:70]
            print(f"  ✗ {r['company']:35s} [{r['ats_type']:15s}]{enabled_tag}  {err}")

    if blocked:
        print("\nBLOCKED:")
        for r in sorted(blocked, key=lambda x: x["ats_type"]):
            err = (r.get("error") or "")[:70]
            print(f"  ⊘ {r['company']:35s} [{r['ats_type']:15s}]  {err}")

    print(f"\nFull results saved to: {STATUS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
