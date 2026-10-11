"""A/B test measuring coverage impact of an honest User-Agent vs Chrome UA (DECISIONS D14).

Runs sampled boards twice (Chrome UA first, then honest UA) and compares discovered job URLs.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import random
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.monitor import monitor_one
from src.core.monitors import monitor_needs_browser
from src.logger import get_logger
from src.shared.http import DEFAULT_USER_AGENT, create_http_client
from src.shared.robots import API_MONITORS

log = get_logger("ua_ab_test")

HONEST_USER_AGENT = "myjobs-bot/0.1 (+https://github.com/brohan2001/myjobs)"
DEFAULT_TIMEOUT_S = 60.0


def extract_host(url: str, monitor_type: str = "") -> str:
    """Extract throttle host for a board.

    For API monitors, boards belonging to the same ATS share the ATS API domain
    (e.g., all greenhouse boards hit boards-api.greenhouse.io).
    For site-reading monitors, extract the hostname from board_url.
    """
    if monitor_type and monitor_type in API_MONITORS:
        return f"ats:{monitor_type}"
    parsed = urlparse(url)
    return (parsed.hostname or parsed.netloc or url).lower()


def sample_boards(rows: list[dict], n: int = 200, seed: int = 7) -> list[dict]:
    """Deterministically sample n boards.

    Requirements:
    - About half API monitors, half site-reading monitors.
    - At most one board per company.
    - Skip browser boards (using monitor_needs_browser).
    """
    if n <= 0:
        return []

    # 1. Filter out browser boards
    valid: list[dict] = []
    for r in rows:
        m_type = r.get("monitor_type", "")
        raw_cfg = r.get("monitor_config")
        cfg = json.loads(raw_cfg) if isinstance(raw_cfg, str) and raw_cfg else (raw_cfg or {})
        if not monitor_needs_browser(m_type, cfg):
            valid.append(r)

    # 2. Partition into API and site-reading monitors
    api_rows = [r for r in valid if r.get("monitor_type") in API_MONITORS]
    site_rows = [r for r in valid if r.get("monitor_type") not in API_MONITORS]

    # 3. Stable sort before shuffling to guarantee deterministic order
    sort_key = lambda r: (r.get("company_slug") or "", r.get("board_slug") or "")
    api_rows.sort(key=sort_key)
    site_rows.sort(key=sort_key)

    rng = random.Random(seed)
    rng.shuffle(api_rows)
    rng.shuffle(site_rows)

    target_site = n // 2
    target_api = n - target_site

    selected_site: list[dict] = []
    used_companies: set[str] = set()

    for r in site_rows:
        comp = r.get("company_slug") or r.get("board_slug")
        if comp not in used_companies:
            used_companies.add(comp)
            selected_site.append(r)
            if len(selected_site) >= target_site:
                break

    selected_api: list[dict] = []
    for r in api_rows:
        comp = r.get("company_slug") or r.get("board_slug")
        if comp not in used_companies:
            used_companies.add(comp)
            selected_api.append(r)
            if len(selected_api) >= target_api:
                break

    # If either category lacked enough unique companies, backfill from the other
    if len(selected_site) + len(selected_api) < n:
        for r in api_rows:
            comp = r.get("company_slug") or r.get("board_slug")
            if comp not in used_companies:
                used_companies.add(comp)
                selected_api.append(r)
                if len(selected_api) + len(selected_site) >= n:
                    break

    if len(selected_site) + len(selected_api) < n:
        for r in site_rows:
            comp = r.get("company_slug") or r.get("board_slug")
            if comp not in used_companies:
                used_companies.add(comp)
                selected_site.append(r)
                if len(selected_api) + len(selected_site) >= n:
                    break

    combined = selected_api + selected_site
    rng.shuffle(combined)
    return combined


def classify(chrome: dict, honest: dict) -> str:
    """Classify comparison between Chrome UA and Honest UA results.

    Possible classifications:
    - 'same': both ok, job counts within 10% or ±2
    - 'honest_blocked': chrome ok with >= 1 job; honest errors or 0 jobs
    - 'honest_fewer': both ok, honest < 90% of chrome (and not 'same')
    - 'chrome_blocked': honest ok with >= 1 job; chrome errors or 0 jobs
    - 'both_failed': both errored, or both failed to get jobs with at least one error
    - 'honest_more': both ok, honest > 110% of chrome (and not 'same')
    """
    c_err = chrome.get("error")
    h_err = honest.get("error")
    c_jobs = chrome.get("jobs")
    h_jobs = honest.get("jobs")

    c_ok = (c_err is None)
    h_ok = (h_err is None)
    c_count = c_jobs if c_jobs is not None else 0
    h_count = h_jobs if h_jobs is not None else 0

    # If both errored
    if not c_ok and not h_ok:
        return "both_failed"

    # Blocked checks (one has >=1 job, other errored or got 0)
    if c_ok and c_count >= 1 and (not h_ok or h_count == 0):
        return "honest_blocked"

    if h_ok and h_count >= 1 and (not c_ok or c_count == 0):
        return "chrome_blocked"

    # If one errored and the other got 0 jobs
    if not c_ok or not h_ok:
        return "both_failed"

    # Both are ok (no errors)
    diff = abs(c_count - h_count)

    # Within ±2
    if diff <= 2:
        return "same"

    # Within 10% (relative to chrome count)
    if c_count > 0 and (0.9 * c_count <= h_count <= 1.1 * c_count):
        return "same"

    # honest_fewer: honest < 90% of chrome
    if c_count > 0 and h_count < 0.9 * c_count:
        return "honest_fewer"

    # honest_more: honest > 110% of chrome
    if h_count > c_count:
        return "honest_more"

    return "same"


async def _run_single_monitor(
    board_url: str,
    monitor_type: str,
    config: dict,
    client: httpx.AsyncClient,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> tuple[int | None, str | None]:
    """Execute monitor_one with a timeout, returning (job_count, error_str)."""
    try:
        res = await asyncio.wait_for(
            monitor_one(board_url, monitor_type, config, client),
            timeout=timeout,
        )
        return len(res.urls), None
    except Exception as exc:
        msg = str(exc).strip()
        err_msg = f"{type(exc).__name__}: {msg[:120]}" if msg else f"{type(exc).__name__}: timed out after {int(timeout)}s"
        return None, err_msg


async def run_board(
    board: dict,
    chrome_client: httpx.AsyncClient,
    honest_client: httpx.AsyncClient,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """Run Chrome UA first, then honest UA for a single board."""
    board_slug = board.get("board_slug", "")
    board_url = board.get("board_url", "")
    monitor_type = board.get("monitor_type", "")
    raw_config = board.get("monitor_config")
    config = json.loads(raw_config) if isinstance(raw_config, str) and raw_config else (raw_config or {})
    kind = "api" if monitor_type in API_MONITORS else "site"

    # 1. Chrome UA
    chrome_jobs, chrome_err = await _run_single_monitor(
        board_url, monitor_type, config, chrome_client, timeout=timeout
    )

    # 2. Honest UA
    honest_jobs, honest_err = await _run_single_monitor(
        board_url, monitor_type, config, honest_client, timeout=timeout
    )

    chrome_data = {"jobs": chrome_jobs, "error": chrome_err}
    honest_data = {"jobs": honest_jobs, "error": honest_err}
    classification = classify(chrome_data, honest_data)

    return {
        "board_slug": board_slug,
        "monitor_type": monitor_type,
        "kind": kind,
        "chrome": chrome_data,
        "honest": honest_data,
        "classification": classification,
    }


def build_summary(records: list[dict]) -> dict:
    """Build summary counts and list of honest_blocked boards."""
    categories = [
        "same",
        "honest_blocked",
        "honest_fewer",
        "chrome_blocked",
        "both_failed",
        "honest_more",
    ]
    summary: dict[str, Any] = {
        "total": len(records),
        "api_total": sum(1 for r in records if r.get("kind") == "api"),
        "site_total": sum(1 for r in records if r.get("kind") == "site"),
        "counts": {cat: 0 for cat in categories},
        "by_kind": {
            "api": {cat: 0 for cat in categories},
            "site": {cat: 0 for cat in categories},
        },
        "honest_blocked": [
            {
                "board_slug": r.get("board_slug"),
                "monitor_type": r.get("monitor_type"),
                "kind": r.get("kind"),
                "chrome_jobs": r.get("chrome", {}).get("jobs"),
                "honest_jobs": r.get("honest", {}).get("jobs"),
                "honest_error": r.get("honest", {}).get("error"),
            }
            for r in records
            if r.get("classification") == "honest_blocked"
        ],
    }

    for r in records:
        cat = r.get("classification") or classify(r.get("chrome", {}), r.get("honest", {}))
        if cat in summary["counts"]:
            summary["counts"][cat] += 1
        kind = r.get("kind", "site")
        if kind in summary["by_kind"] and cat in summary["by_kind"][kind]:
            summary["by_kind"][kind][cat] += 1

    return summary


def generate_markdown_report(records: list[dict], summary: dict, date_str: str) -> str:
    """Generate Markdown report summarizing A/B test results."""
    categories = [
        "same",
        "honest_blocked",
        "honest_fewer",
        "chrome_blocked",
        "both_failed",
        "honest_more",
    ]
    total = summary["total"]
    api_total = summary["api_total"]
    site_total = summary["site_total"]

    lines = [
        f"# User-Agent A/B Test Report ({date_str})",
        "",
        f"**Sample size:** {total} boards (API: {api_total}, Site: {site_total})",
        "",
        "## Summary by Classification",
        "",
        "| Classification | API | Site | Total | % of Total |",
        "|----------------|-----|------|-------|------------|",
    ]

    for cat in categories:
        api_count = summary["by_kind"]["api"].get(cat, 0)
        site_count = summary["by_kind"]["site"].get(cat, 0)
        cat_total = summary["counts"].get(cat, 0)
        pct = (cat_total / total * 100) if total > 0 else 0.0
        lines.append(f"| {cat:<14} | {api_count:3d} | {site_count:4d} | {cat_total:5d} | {pct:9.1f}% |")

    lines.append(f"| **Total**        | {api_total:3d} | {site_total:4d} | {total:5d} |    100.0% |")
    lines.append("")

    honest_blocked = summary["honest_blocked"]
    lines.append(f"## Honest Blocked Boards ({len(honest_blocked)})")
    lines.append("")
    if not honest_blocked:
        lines.append("No boards were classified as honest_blocked.")
    else:
        lines.append("| Board Slug | Monitor Type | Kind | Chrome Jobs | Honest Jobs | Honest Error |")
        lines.append("|------------|--------------|------|-------------|-------------|--------------|")
        for b in honest_blocked:
            slug = b.get("board_slug", "")
            m_type = b.get("monitor_type", "")
            kind = b.get("kind", "")
            c_j = str(b.get("chrome_jobs", ""))
            h_j = str(b.get("honest_jobs", ""))
            h_e = str(b.get("honest_error") or "")
            lines.append(f"| {slug} | {m_type} | {kind} | {c_j} | {h_j} | {h_e} |")

    lines.append("")
    return "\n".join(lines)


def print_summary_table(summary: dict) -> None:
    """Print the final summary table to stdout."""
    categories = [
        "same",
        "honest_blocked",
        "honest_fewer",
        "chrome_blocked",
        "both_failed",
        "honest_more",
    ]
    total = summary["total"]
    api_total = summary["api_total"]
    site_total = summary["site_total"]

    print()
    print("=" * 60)
    print(f"User-Agent A/B Test Summary (Total: {total})")
    print("=" * 60)
    print(f"{'Classification':<16} | {'API':<5} | {'Site':<5} | {'Total':<6} | {'%':<7}")
    print("-" * 60)
    for cat in categories:
        api_count = summary["by_kind"]["api"].get(cat, 0)
        site_count = summary["by_kind"]["site"].get(cat, 0)
        cat_total = summary["counts"].get(cat, 0)
        pct = (cat_total / total * 100) if total > 0 else 0.0
        print(f"{cat:<16} | {api_count:<5} | {site_count:<5} | {cat_total:<6} | {pct:>5.1f}%")
    print("-" * 60)
    print(f"{'Total':<16} | {api_total:<5} | {site_total:<5} | {total:<6} | {'100.0%':>6}")
    print("=" * 60)
    blocked_count = len(summary["honest_blocked"])
    print(f"Honest blocked boards: {blocked_count}")
    print()


async def run_ab_test(
    boards: list[dict],
    concurrency: int = 6,
    chrome_client: httpx.AsyncClient | None = None,
    honest_client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> list[dict]:
    """Run A/B test over sampled boards with bounded concurrency and host locking."""
    close_clients = False
    if chrome_client is None or honest_client is None:
        close_clients = True
        chrome_client = create_http_client()
        chrome_client.headers["User-Agent"] = DEFAULT_USER_AGENT
        honest_client = create_http_client()
        honest_client.headers["User-Agent"] = HONEST_USER_AGENT

    sem = asyncio.Semaphore(concurrency)
    host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def worker(board: dict) -> dict:
        host = extract_host(board.get("board_url", ""), board.get("monitor_type", ""))
        async with host_locks[host]:
            async with sem:
                log.info("ua_ab.board_start", board_slug=board.get("board_slug"), host=host)
                res = await run_board(board, chrome_client, honest_client, timeout=timeout)
                log.info(
                    "ua_ab.board_done",
                    board_slug=board.get("board_slug"),
                    classification=res["classification"],
                    chrome_jobs=res["chrome"]["jobs"],
                    honest_jobs=res["honest"]["jobs"],
                )
                return res

    try:
        results = await asyncio.gather(*[worker(b) for b in boards])
    finally:
        if close_clients:
            await chrome_client.aclose()
            await honest_client.aclose()

    return results


async def async_main(args: argparse.Namespace) -> None:
    boards_file = Path(args.boards)
    if not boards_file.is_file():
        log.error("boards_file_not_found", path=str(boards_file))
        sys.exit(1)

    with open(boards_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    log.info("ua_ab.loaded_boards", total_rows=len(rows))
    sampled = sample_boards(rows, n=args.sample, seed=args.seed)
    log.info("ua_ab.sampled_boards", sampled_count=len(sampled))

    records = await run_ab_test(sampled, concurrency=args.concurrency)
    summary = build_summary(records)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = date.today().isoformat()

    json_path = out_dir / f"{date_str}.json"
    md_path = out_dir / f"{date_str}.md"

    data_payload = {
        "date": date_str,
        "sample_size": len(sampled),
        "seed": args.seed,
        "concurrency": args.concurrency,
        "summary": summary,
        "records": records,
    }

    json_path.write_text(json.dumps(data_payload, indent=2), encoding="utf-8")
    log.info("ua_ab.saved_json", path=str(json_path))

    md_content = generate_markdown_report(records, summary, date_str)
    md_path.write_text(md_content, encoding="utf-8")
    log.info("ua_ab.saved_md", path=str(md_path))

    # Print summary table at the end
    print_summary_table(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="User-Agent A/B test on job board monitors (D14)")
    parser.add_argument("--sample", type=int, default=200, help="Number of boards to sample (default: 200)")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for sampling (default: 7)")
    parser.add_argument("--concurrency", type=int, default=6, help="Max concurrency for board runs (default: 6)")
    parser.add_argument("--out", type=str, default="docs/research/ua_ab", help="Output directory (default: docs/research/ua_ab)")
    parser.add_argument("--boards", type=str, default="data/boards.csv", help="Path to boards.csv")
    args = parser.parse_args()

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
