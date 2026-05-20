#!/usr/bin/env python3
"""
Validate that the 102 curated companies return ≥1 job via the jobseek pipeline.
Reads company slugs from scripts/scraping_status.json and boards from data/boards.csv.

Run from project root: python scripts/validate_102_companies.py

Exit code 0 = all passed, 1 = some failures.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.companies import load_boards
from src.core.monitor import monitor_one_stream
from src.core.monitors import monitor_needs_browser
from src.shared.http import create_http_client

STATUS_JSON = Path(__file__).parent / "scraping_status.json"

Result = dict  # {company, slug, ats_type, enabled, checked_at, jobs, status, error}

_TIMEOUTS: dict[str, int] = {
    "workday":    120,  # multi-site discovery can be slow
    "api_sniffer": 60,
    "dom":        60,
    "eightfold":  45,
    "ashby":      45,
    "amazon":     45,
    "apple":      60,
    "microsoft":  45,
}
_DEFAULT_TIMEOUT = 35


async def _test_board(board, http, pw=None) -> tuple[int, str | None]:
    """Test one board; returns (job_count, error_or_None).

    Breaks after the first non-empty batch — we only need to confirm ≥1 job.
    """
    timeout = _TIMEOUTS.get(board.monitor_type, _DEFAULT_TIMEOUT)
    count = 0
    try:
        async def _collect():
            nonlocal count
            async for batch in monitor_one_stream(
                board.board_url, board.monitor_type, board.monitor_config, http, pw=pw
            ):
                n = len(batch.jobs_by_url) if batch.jobs_by_url else len(batch.urls)
                count += n
                if count > 0:
                    break  # confirmed ≥1 job — no need to fetch all pages

        await asyncio.wait_for(_collect(), timeout=timeout)
        if count == 0:
            return 0, "0 jobs returned"
        return count, None
    except asyncio.TimeoutError:
        return count, f"TIMEOUT after {timeout}s"
    except Exception as e:
        return count, str(e)[:200]


async def _test_company(slug: str, boards: list, sem: asyncio.Semaphore, http, pw=None) -> Result:
    """Test all boards for a company; pass if any returns ≥1 job."""
    company_name = boards[0].company.name if boards[0].company else slug
    best_count = 0
    best_error: str | None = None
    primary_type = boards[0].monitor_type

    async with sem:
        for board in boards:
            count, error = await _test_board(board, http, pw=pw)
            if count > best_count:
                best_count = count
                primary_type = board.monitor_type
            if error is not None:
                best_error = error  # always capture the last real error
            if count > 0:
                best_error = None
                break  # company passes — no need to test remaining boards

    return {
        "company": company_name,
        "slug": slug,
        "ats_type": primary_type,
        "enabled": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "jobs": best_count,
        "status": "pass" if best_count > 0 else "fail",
        "error": best_error if best_count == 0 else None,
    }


async def main() -> int:
    with open(STATUS_JSON) as f:
        existing: dict = json.load(f)

    target_slugs = set(existing.keys())

    all_boards = load_boards()
    by_company: dict[str, list] = {}
    for board in all_boards:
        if board.company_slug in target_slugs:
            by_company.setdefault(board.company_slug, []).append(board)

    missing = target_slugs - set(by_company.keys())
    if missing:
        print(f"WARNING: {len(missing)} slugs not found in boards.csv: {sorted(missing)}")

    total = len(by_company)
    print(f"\n{'='*70}")
    print(f"  Validating {total} companies via jobseek monitors")
    print(f"{'='*70}\n")

    needs_browser = any(
        monitor_needs_browser(b.monitor_type, b.monitor_config)
        for boards in by_company.values()
        for b in boards
    )

    # Ashby and Workday are rate-sensitive — run sequentially to avoid 429s / rate limits
    sequential_slugs = {
        slug for slug, boards in by_company.items()
        if any(b.monitor_type in ("ashby", "workday") for b in boards)
    }
    concurrent_slugs = set(by_company.keys()) - sequential_slugs

    sem = asyncio.Semaphore(10)
    http = create_http_client()
    results: dict[str, Result] = {}

    def _print_result(r: Result) -> None:
        icon = "✓" if r["status"] == "pass" else "✗"
        jobs_str = f"{r['jobs']:>4}" if r["jobs"] else "   0"
        print(f"  {icon} {r['company']:<35} {r['ats_type']:<18} {jobs_str} jobs")

    async def run_all(pw=None):
        # Concurrent for non-rate-sensitive monitors
        tasks = [
            _test_company(slug, by_company[slug], sem, http, pw=pw)
            for slug in concurrent_slugs
        ]
        for coro in asyncio.as_completed(tasks):
            r = await coro
            results[r["slug"]] = r
            _print_result(r)

        # Sequential for rate-sensitive monitors (Ashby, Workday)
        for slug in sorted(sequential_slugs):
            r = await _test_company(slug, by_company[slug], sem, http, pw=pw)
            results[r["slug"]] = r
            _print_result(r)

    if needs_browser:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            await run_all(pw=pw)
    else:
        await run_all()

    await http.aclose()

    passed = [r for r in results.values() if r["status"] == "pass"]
    failed = [r for r in results.values() if r["status"] == "fail"]

    print(f"\n{'='*70}")
    print(f"RESULT: {len(passed)}/{total} Companies Passed (>0 jobs found)")
    print(f"{'='*70}")

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for r in sorted(failed, key=lambda x: x["ats_type"]):
            err = f" — {r['error']}" if r["error"] else " — 0 jobs returned"
            print(f"  ✗ {r['company']:<35} {r['ats_type']:<18}{err}")

    # Update status file — preserve disabled entries, overwrite checked ones
    final = dict(existing)
    final.update(results)
    with open(STATUS_JSON, "w") as f:
        json.dump(final, f, indent=2)
    print(f"\nUpdated {STATUS_JSON}")
    print()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
