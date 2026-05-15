#!/usr/bin/env python3
"""
Validate that all companies in companies.json return ≥1 job.
Run from project root: python scripts/validate_102_companies.py

Exit code 0 = all passed, 1 = some failures.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_companies
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.amazon import AmazonScraper
from src.scrapers.apple import AppleScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.microsoft import MicrosoftScraper
from src.scrapers.workable import WorkableScraper
from src.scrapers.rippling import RipplingScraper
from src.scrapers.smartrecruiters import SmartRecruitersScraper
from src.scrapers.serp_fallback import SerpFallbackScraper

# Timeouts per ATS type (seconds)
_TIMEOUTS = {
    "greenhouse": 30,
    "lever":      30,
    "ashby":      45,
    "amazon":     45,
    "microsoft":  45,
    "workday":    60,
    "apple":      60,
    "workable":   30,
    "rippling":         45,
    "smartrecruiters":  30,
    "serp":             60,
}

_DUMMY_CID = 999  # dummy company_id for validation

Result = dict  # {name, ats, count, elapsed, error}


async def _test_one(scraper, company: dict, timeout: int) -> Result:
    name = company["name"]
    ats = company["ats_type"]
    t0 = time.monotonic()
    try:
        jobs = await asyncio.wait_for(
            scraper.fetch_jobs(company, _DUMMY_CID),
            timeout=timeout,
        )
        count = len(jobs) if jobs else 0
        error = ""
    except asyncio.TimeoutError:
        count = 0
        error = f"TIMEOUT after {timeout}s"
    except Exception as e:
        count = 0
        error = str(e)[:120]
    elapsed = time.monotonic() - t0
    return {"name": name, "ats": ats, "count": count, "elapsed": elapsed, "error": error}


async def _run_group_concurrent(
    scraper_cls, companies: list[dict], sem_limit: int = 10
) -> list[Result]:
    """Run a group of companies through a shared scraper instance concurrently."""
    results = []
    sem = asyncio.Semaphore(sem_limit)

    async with scraper_cls() as scraper:
        async def run_one(c):
            async with sem:
                ats = c["ats_type"]
                return await _test_one(scraper, c, _TIMEOUTS.get(ats, 60))

        tasks = [run_one(c) for c in companies]
        results = await asyncio.gather(*tasks)

    return list(results)


async def _run_group_sequential(scraper_cls, companies: list[dict]) -> list[Result]:
    """Run a group of companies through a shared scraper instance sequentially."""
    results = []
    async with scraper_cls() as scraper:
        for c in companies:
            ats = c["ats_type"]
            r = await _test_one(scraper, c, _TIMEOUTS.get(ats, 60))
            results.append(r)
    return results


def _print_row(r: Result, status: str) -> None:
    icon = "✓" if status == "PASS" else "✗"
    jobs_str = f"{r['count']:>4} jobs" if r["count"] else "   0 jobs"
    elapsed_str = f"{r['elapsed']:>5.1f}s"
    err = f"  [{r['error']}]" if r["error"] else ""
    print(f"  {icon} {r['name']:<35} {r['ats']:<12} {jobs_str}  {elapsed_str}{err}")


async def main() -> int:
    companies = load_companies()

    # Group by ATS type
    by_type: dict[str, list[dict]] = {}
    for c in companies:
        by_type.setdefault(c["ats_type"], []).append(c)

    all_results: list[Result] = []
    total = len(companies)

    print(f"\n{'='*70}")
    print(f"  Validating {total} companies across {len(by_type)} ATS types")
    print(f"{'='*70}\n")

    # ── Greenhouse (concurrent) ───────────────────────────────────────────────
    gh = by_type.get("greenhouse", [])
    if gh:
        print(f"[Greenhouse — {len(gh)} companies]")
        results = await _run_group_concurrent(GreenhouseScraper, gh, sem_limit=10)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Ashby (sequential — rate-sensitive, returns 429 under concurrent load) ─
    ab = by_type.get("ashby", [])
    if ab:
        print(f"\n[Ashby — {len(ab)} companies]")
        results = await _run_group_sequential(AshbyScraper, ab)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Lever (sequential) ────────────────────────────────────────────────────
    lv = by_type.get("lever", [])
    if lv:
        print(f"\n[Lever — {len(lv)} companies]")
        results = await _run_group_sequential(LeverScraper, lv)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Amazon (sequential) ───────────────────────────────────────────────────
    az = by_type.get("amazon", [])
    if az:
        print(f"\n[Amazon — {len(az)} companies]")
        results = await _run_group_sequential(AmazonScraper, az)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Microsoft (sequential) ────────────────────────────────────────────────
    ms = by_type.get("microsoft", [])
    if ms:
        print(f"\n[Microsoft — {len(ms)} companies]")
        results = await _run_group_sequential(MicrosoftScraper, ms)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Apple (sequential) ────────────────────────────────────────────────────
    ap = by_type.get("apple", [])
    if ap:
        print(f"\n[Apple — {len(ap)} companies]")
        results = await _run_group_sequential(AppleScraper, ap)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Workday (sequential — one shared Playwright browser) ─────────────────
    wd = by_type.get("workday", [])
    if wd:
        print(f"\n[Workday — {len(wd)} companies]")
        results = await _run_group_sequential(WorkdayScraper, wd)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Workable (sequential) ─────────────────────────────────────────────────
    wb = by_type.get("workable", [])
    if wb:
        print(f"\n[Workable — {len(wb)} companies]")
        results = await _run_group_sequential(WorkableScraper, wb)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Rippling (sequential) ─────────────────────────────────────────────────
    rp = by_type.get("rippling", [])
    if rp:
        print(f"\n[Rippling — {len(rp)} companies]")
        results = await _run_group_sequential(RipplingScraper, rp)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── SmartRecruiters (sequential) ──────────────────────────────────────────
    sr = by_type.get("smartrecruiters", [])
    if sr:
        print(f"\n[SmartRecruiters — {len(sr)} companies]")
        results = await _run_group_sequential(SmartRecruitersScraper, sr)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── SERP fallback (Google, Meta) ──────────────────────────────────────────
    serp = by_type.get("serp", [])
    if serp:
        print(f"\n[SERP — {len(serp)} companies]")
        results = await _run_group_sequential(SerpFallbackScraper, serp)
        for r in results:
            _print_row(r, "PASS" if r["count"] > 0 else "FAIL")
        all_results.extend(results)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = [r for r in all_results if r["count"] > 0]
    failed = [r for r in all_results if r["count"] == 0]

    print(f"\n{'='*70}")
    print(f"RESULT: {len(passed)}/{total} Companies Passed (>0 jobs found)")
    print(f"{'='*70}")

    if failed:
        print(f"\nFailed companies ({len(failed)}):")
        for r in sorted(failed, key=lambda x: x["ats"]):
            err = f" — {r['error']}" if r["error"] else " — 0 jobs returned"
            print(f"  ✗ {r['name']:<35} {r['ats']:<12}{err}")

    print()
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
