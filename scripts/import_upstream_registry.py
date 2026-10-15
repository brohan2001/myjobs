"""Import jobseek's company registry and keep only boards with tech jobs (DECISIONS D27, D28).

    python scripts/import_upstream_registry.py                 # probe every board, print the summary
    python scripts/import_upstream_registry.py --browser       # also probe boards that need Playwright
    python scripts/import_upstream_registry.py --apply         # write data/companies.csv + data/boards.csv

Steps:
1. Fetch ``apps/crawler/data/{companies,boards}.csv`` at ``--sha``. Upstream's version wins for boards
   in both registries (it has the newer fixes); boards only we have are kept.
2. Probe each board once with its monitor. Rich monitors give titles. URL-only monitors give
   URLs, whose slugs stand in for titles ("…/job/Bengaluru/Software-Engineer_R123").
3. Keep a board if any title is tech (``src.core.tech_gate``), or if there's too little evidence to
   judge (fewer than ``MIN_EVIDENCE`` titles, a probe error, or browser boards without --browser).
   Drop it when robots.txt forbids it, or when ``MIN_EVIDENCE``+ titles are all non-tech.
4. A company stays if any of its boards stays.

Probe results are cached in ``output/vetting.jsonl``, so a rerun resumes and ``--apply`` is instant.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.monitor import monitor_one  # noqa: E402
from src.core.monitors import monitor_needs_browser  # noqa: E402
from src.core.tech_gate import is_tech_title, title_from_url  # noqa: E402
from src.logger import get_logger  # noqa: E402
from src.shared.http import HONEST_USER_AGENT, create_http_client  # noqa: E402
from src.shared.robots import RobotsDisallowedError, ensure_allowed  # noqa: E402

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "output" / "vetting.jsonl"
UPSTREAM_SHA = "cf71baa66147eb825c9569bfa70be87be7e92c91"  # keep in step with docs/UPSTREAM.md
RAW = "https://raw.githubusercontent.com/colophon-group/jobseek/{sha}/apps/crawler/data/{name}.csv"

MIN_EVIDENCE = 3  # titles needed before "no tech titles" counts as evidence
MAX_TITLES = 200  # titles judged per board
PROBE_TIMEOUT_S = 180
CONCURRENCY = 24
PER_HOST = 2
BROWSER_CONCURRENCY = 2

BOARD_FIELDS = ["company_slug", "board_slug", "board_url", "monitor_type", "monitor_config", "scraper_type", "scraper_config"]
COMPANY_FIELDS = ["slug", "name", "website", "industry", "tier", "enabled", "country", "hq_city", "company_type"]

def verdict(titles: list[str], error: str | None) -> tuple[bool, str]:
    """(keep, reason) for one board's probe."""
    if error == "robots":
        return False, "dropped: robots.txt disallows"
    if error:
        return True, "kept: probe failed"
    if any(is_tech_title(t) for t in titles):
        return True, "kept: has tech titles"
    if len(titles) < MIN_EVIDENCE:
        return True, "kept: too few titles to judge"
    return False, "dropped: no tech titles"


def fetch_csv(client: httpx.Client, sha: str, name: str) -> list[dict]:
    resp = client.get(RAW.format(sha=sha, name=name))
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge(upstream_boards: list[dict], upstream_companies: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """Upstream boards (newer) plus boards only we have; companies keyed by slug, ours first."""
    ours = read_csv(DATA / "boards.csv")
    upstream_slugs = {b["board_slug"] for b in upstream_boards}
    boards = [{k: b.get(k, "") for k in BOARD_FIELDS} for b in upstream_boards]
    boards += [b for b in ours if b["board_slug"] not in upstream_slugs]

    companies = {c["slug"]: c for c in read_csv(DATA / "companies.csv")}
    for c in upstream_companies:
        if c["slug"] not in companies:
            companies[c["slug"]] = {
                "slug": c["slug"], "name": c["name"], "website": c["website"], "industry": c["industry"],
                "tier": "", "enabled": "true", "country": "", "hq_city": "", "company_type": "",
            }
    return boards, companies


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    with CACHE.open(encoding="utf-8") as f:
        return {r["board_slug"]: r for r in map(json.loads, f)}


async def probe(board: dict, http: httpx.AsyncClient, pw) -> dict:
    """Run the board's monitor once; return titles (or URL-slug titles) and any error."""
    config = json.loads(board["monitor_config"] or "{}")
    out = {"board_slug": board["board_slug"], "titles": [], "jobs": 0, "error": None}
    try:
        await ensure_allowed(http, board["board_url"], board["monitor_type"])
        result = await asyncio.wait_for(
            monitor_one(board["board_url"], board["monitor_type"], config, http, pw=pw), PROBE_TIMEOUT_S
        )
    except RobotsDisallowedError:
        out["error"] = "robots"
        return out
    except Exception as exc:  # noqa: BLE001 - any failure leaves the board unjudged
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return out
    out["jobs"] = len(result.urls)
    if result.jobs_by_url:
        titles = [j.title for j in result.jobs_by_url.values() if j.title]
    else:
        titles = [t for t in map(title_from_url, sorted(result.urls)) if t]
    out["titles"] = titles[:MAX_TITLES]
    return out


async def probe_all(boards: list[dict], *, browser: bool) -> dict[str, dict]:
    results = load_cache()
    todo = []
    for b in boards:
        if b["board_slug"] in results:
            continue
        needs_browser = monitor_needs_browser(b["monitor_type"], json.loads(b["monitor_config"] or "{}"))
        if needs_browser and not browser:
            continue
        todo.append((b, needs_browser))
    log.info("vetting.start", extra={"cached": len(results), "to_probe": len(todo)})
    if not todo:
        return results

    gate = asyncio.Semaphore(CONCURRENCY)
    browser_gate = asyncio.Semaphore(BROWSER_CONCURRENCY)
    hosts: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(PER_HOST))
    pw = None
    if browser and any(nb for _, nb in todo):
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
    CACHE.parent.mkdir(exist_ok=True)
    done = 0
    with CACHE.open("a", encoding="utf-8") as cache:

        async def one(board: dict, needs_browser: bool) -> None:
            nonlocal done
            host = urlparse(board["board_url"]).hostname or ""
            async with gate, hosts[host]:
                if needs_browser:
                    async with browser_gate:
                        r = await probe(board, http, pw)
                else:
                    r = await probe(board, http, None)
            results[board["board_slug"]] = r
            cache.write(json.dumps(r) + "\n")
            cache.flush()
            done += 1
            if done % 100 == 0:
                log.info("vetting.progress", extra={"done": done, "of": len(todo)})

        try:
            async with create_http_client() as http:
                await asyncio.gather(*(one(b, nb) for b, nb in todo))
        finally:
            if pw is not None:
                await pw.stop()
    return results


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sha", default=UPSTREAM_SHA)
    ap.add_argument("--browser", action="store_true", help="probe boards that need Playwright too")
    ap.add_argument("--apply", action="store_true", help="write the vetted registry to data/")
    args = ap.parse_args()

    with httpx.Client(headers={"User-Agent": HONEST_USER_AGENT}, timeout=60) as client:
        upstream_boards = fetch_csv(client, args.sha, "boards")
        upstream_companies = fetch_csv(client, args.sha, "companies")
    boards, companies = merge(upstream_boards, upstream_companies)
    results = asyncio.run(probe_all(boards, browser=args.browser))

    kept, reasons = [], Counter()
    for b in boards:
        r = results.get(b["board_slug"])
        keep, reason = verdict(r["titles"], r["error"]) if r else (True, "kept: not probed (needs browser)")
        reasons[reason] += 1
        if keep:
            kept.append(b)
    kept_companies = {b["company_slug"] for b in kept}
    print(f"boards: {len(boards)} → kept {len(kept)}; companies: {len(companies)} → kept {len(kept_companies)}")
    for reason, n in reasons.most_common():
        print(f"  {n:6d}  {reason}")
    print("monitor types in use:", len({b['monitor_type'] for b in kept}))

    if args.apply:
        write_csv(DATA / "boards.csv", BOARD_FIELDS, sorted(kept, key=lambda b: (b["company_slug"], b["board_slug"])))
        write_csv(DATA / "companies.csv", COMPANY_FIELDS,
                  [companies[s] for s in sorted(kept_companies) if s in companies])
        print("wrote data/boards.csv and data/companies.csv")


if __name__ == "__main__":
    main()
