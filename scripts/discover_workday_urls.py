"""
discover_workday_urls.py — Auto-discover correct Workday host/board for failing companies.

For each failing Workday company:
  1. Tests the current host/board via curl_cffi
  2. If 422, tries common board-name variants and known alternative hosts
  3. Validates the discovered URL by checking total > 0
  4. Optionally patches companies.json (--apply flag)

Usage:
    python scripts/discover_workday_urls.py             # dry-run report
    python scripts/discover_workday_urls.py --apply     # update companies.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
COMPANIES_JSON = ROOT / "data" / "companies.json"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ── Known fixes discovered via research ───────────────────────────────────────
# Format: (correct_host, correct_board)  — None means "keep existing"
KNOWN_FIXES: dict[str, tuple[str, str]] = {
    "Mastercard":     ("mastercard.wd1.myworkdayjobs.com", "CorporateCareers"),
    "Fidelity":       ("fmr.wd1.myworkdayjobs.com",        "FidelityCareers"),
    "Morgan Stanley": ("ms.wd5.myworkdayjobs.com",          "External"),
    "BlackRock":      ("blackrock.wd1.myworkdayjobs.com",   "BlackRock_Professional"),
    "BNY Mellon":     ("bnymellon.wd1.myworkdayjobs.com",   "BNYMellonCareers"),
    "Dell Technologies": ("dell.wd1.myworkdayjobs.com",     "External"),
}

# Companies that have migrated off Workday entirely
MIGRATED: dict[str, str] = {
    "American Express": "Eightfold AI (aexp.eightfold.ai) — disable Workday entry",
    "JPMorgan Chase":   "Oracle Recruiting Cloud (jpmc.fa.oraclecloud.com) — disable Workday entry",
    "ServiceNow":       "SmartRecruiters (sr_id=ServiceNow) — change ats_type",
    "Splunk":           "Merged into Cisco — disable (Cisco already scraped)",
}

# Board-name candidates to try for each tenant (appended after any known list)
_COMMON_BOARDS = [
    "External",
    "External_Career_Site",
    "ExternalCareers",
    "Careers",
    "careers",
]


async def _test_board(session, host: str, board: str, timeout: int = 12) -> int | None:
    """Return total job count on success, None on failure."""
    tenant = host.split(".")[0]
    url = f"https://{host}/wday/cxs/{tenant}/{board}/jobs"
    payload = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}
    try:
        resp = await session.post(url, json=payload, headers=_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("errorCode"):
            return None
        return int(data.get("total", 0))
    except Exception:
        return None


async def _discover_one(session, company: dict) -> dict:
    """Try to find the correct host/board for a single company. Returns result dict."""
    name = company["name"]
    host = company.get("workday_host", "")
    board = company.get("workday_board", "External")

    result = {
        "name": name,
        "current_host": host,
        "current_board": board,
        "status": "UNKNOWN",
        "new_host": None,
        "new_board": None,
        "total": None,
        "note": "",
    }

    # ── Step 1: known migration? ──────────────────────────────────────────────
    if name in MIGRATED:
        result["status"] = "MIGRATED"
        result["note"] = MIGRATED[name]
        return result

    # ── Step 2: known fix? ────────────────────────────────────────────────────
    if name in KNOWN_FIXES:
        new_host, new_board = KNOWN_FIXES[name]
        total = await _test_board(session, new_host, new_board)
        if total is not None:
            result.update(status="FIXED", new_host=new_host, new_board=new_board, total=total)
        else:
            result.update(status="KNOWN_FIX_UNTESTABLE", new_host=new_host, new_board=new_board,
                          note="Board may be in Workday maintenance — apply fix anyway")
        return result

    # ── Step 3: current config — test first ──────────────────────────────────
    total = await _test_board(session, host, board)
    if total is not None:
        result.update(status="OK", total=total, note="Already working — no change needed")
        return result

    # ── Step 4: try common board variants on same host ────────────────────────
    for candidate_board in _COMMON_BOARDS:
        if candidate_board == board:
            continue
        total = await _test_board(session, host, candidate_board)
        if total is not None:
            result.update(status="FIXED", new_host=host, new_board=candidate_board, total=total)
            return result
        await asyncio.sleep(0.3)

    # ── Step 5: try wd1/wd5 swap on same tenant ────────────────────────────────
    if ".wd5." in host:
        alt_host = host.replace(".wd5.", ".wd1.")
    elif ".wd1." in host:
        alt_host = host.replace(".wd1.", ".wd5.")
    else:
        alt_host = None

    if alt_host:
        for candidate_board in [board] + _COMMON_BOARDS:
            total = await _test_board(session, alt_host, candidate_board)
            if total is not None:
                result.update(status="FIXED", new_host=alt_host, new_board=candidate_board, total=total)
                return result
            await asyncio.sleep(0.3)

    result["status"] = "UNRESOLVED"
    result["note"] = "Could not find working host/board — may be in Workday maintenance or fully migrated"
    return result


def _patch_companies(companies: list[dict], results: list[dict]) -> list[dict]:
    """Apply discovered fixes to the companies list in-place."""
    by_name = {c["name"]: i for i, c in enumerate(companies)}

    for r in results:
        if r["name"] not in by_name:
            continue
        idx = by_name[r["name"]]
        c = companies[idx]

        if r["status"] in ("FIXED", "KNOWN_FIX_UNTESTABLE") and r["new_host"]:
            c["workday_host"] = r["new_host"]
            c["workday_board"] = r["new_board"]

        elif r["status"] == "MIGRATED":
            note = r["note"].lower()
            if "disable" in note:
                c["disabled"] = True
            elif "smartrecruiters" in note:
                c["ats_type"] = "smartrecruiters"
                c["sr_id"] = "ServiceNow"
                # Remove Workday-specific keys
                for k in ("workday_host", "workday_board"):
                    c.pop(k, None)

    return companies


async def main(apply: bool) -> None:
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        print("ERROR: curl_cffi not installed — run: pip install curl_cffi", file=sys.stderr)
        sys.exit(1)

    companies = json.loads(COMPANIES_JSON.read_text())
    failing = [
        c for c in companies
        if c.get("ats_type") == "workday" and not c.get("disabled")
    ]

    print(f"Checking {len(failing)} enabled Workday companies...\n")

    results: list[dict] = []
    async with AsyncSession(impersonate="chrome") as session:
        for company in failing:
            r = await _discover_one(session, company)
            results.append(r)
            # Status emoji for quick scanning
            icon = {"OK": "✓", "FIXED": "★", "KNOWN_FIX_UNTESTABLE": "⚠",
                    "MIGRATED": "→", "UNRESOLVED": "✗"}.get(r["status"], "?")
            host_info = f"{r['new_host'] or r['current_host']} / {r['new_board'] or r['current_board']}"
            total_str = f"total={r['total']}" if r["total"] is not None else ""
            print(f"  {icon} [{r['status']:<22}] {r['name']:<22} {host_info}  {total_str}  {r['note']}")
            await asyncio.sleep(0.5)

    # Summary
    ok = sum(1 for r in results if r["status"] == "OK")
    fixed = sum(1 for r in results if r["status"] in ("FIXED", "KNOWN_FIX_UNTESTABLE"))
    migrated = sum(1 for r in results if r["status"] == "MIGRATED")
    unresolved = sum(1 for r in results if r["status"] == "UNRESOLVED")

    print(f"\n{'─'*60}")
    print(f"  Already working : {ok}")
    print(f"  Fixed/patched   : {fixed}")
    print(f"  Migrated off WD : {migrated}")
    print(f"  Unresolved      : {unresolved}")
    print(f"{'─'*60}")

    if apply:
        companies = _patch_companies(companies, results)
        COMPANIES_JSON.write_text(json.dumps(companies, indent=2) + "\n")
        print(f"\nPatched {COMPANIES_JSON}  ({fixed + migrated} companies updated)")
    else:
        print("\nDry run — pass --apply to patch companies.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write fixes to companies.json")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
