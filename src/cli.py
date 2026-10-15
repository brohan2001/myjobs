"""myjobs CLI: keep a public feed of the latest jobs fresh, and serve it."""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import signal
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"
_COMPANIES_CSV = _DATA_DIR / "companies.csv"
_BOARDS_CSV    = _DATA_DIR / "boards.csv"
_COMPANY_FIELDS = ["slug", "name", "website", "industry", "tier", "enabled"]
_BOARD_FIELDS   = ["company_slug", "board_slug", "board_url", "monitor_type", "monitor_config", "scraper_type", "scraper_config"]

_ATS_TO_MONITOR = {
    "greenhouse":      ("greenhouse",      "skip"),
    "lever":           ("lever",           "skip"),
    "ashby":           ("ashby",           "skip"),
    "smartrecruiters": ("smartrecruiters", "skip"),
    "workable":        ("workable",        "skip"),
    "workday":         ("workday",         "workday"),
}

_INDUSTRY_CODES = {"tech": 1, "fintech": 2, "enterprise": 1, "media": 6, "telecom": 7}


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _board_url_for(ats: str, slug: str) -> str:
    urls = {
        "greenhouse":      f"https://job-boards.greenhouse.io/{slug}",
        "lever":           f"https://jobs.lever.co/{slug}",
        "ashby":           f"https://jobs.ashbyhq.com/{slug}",
        "smartrecruiters": f"https://careers.smartrecruiters.com/{slug}",
        "workable":        f"https://apply.workable.com/{slug}/",
    }
    return urls.get(ats, "")


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------


_HARD_EXIT_AFTER_S = 60


def _request_stop(loop: asyncio.AbstractEventLoop, shutdown_event: asyncio.Event) -> None:
    """First signal: drain gracefully, with a hard exit as a backstop. Second signal: exit now.

    The pipeline's drain is bounded, but a task that swallows cancellation (a hung browser
    close) or a pool close can still block forever; on 2026-10-14 a worker ignored SIGTERM
    for over a minute and needed SIGKILL.
    """
    if shutdown_event.is_set():
        console.print("[red]Second stop signal: exiting now.[/red]")
        os._exit(130)
    shutdown_event.set()
    console.print(f"Stopping: draining in-flight work (forced exit after {_HARD_EXIT_AFTER_S} s; Ctrl-C again to force now)")
    loop.call_later(_HARD_EXIT_AFTER_S, os._exit, 1)


async def _run_worker(*, browser: bool, sync_first: bool) -> None:
    """Run the crawl pipeline continuously until SIGINT/SIGTERM.

    Each board reschedules itself every ``check_interval_minutes`` after it is
    monitored, so a long-running worker keeps the feed fresh on its own.
    """
    from src.db import close_all_pools, create_local_pool
    from src.redis_queue import close_redis
    from src.shared.http import create_http_client
    from src.workers.pipeline import run_pipeline

    if sync_first:
        from src.sync import run_sync
        await run_sync()

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_stop, loop, shutdown_event)

    local_pool = await create_local_pool()
    try:
        # create_http_client installs the SSRF guard, default headers and certifi context.
        async with create_http_client() as http:
            runs = [run_pipeline(local_pool, http, shutdown_event, browser=False)]
            if browser:
                runs.append(run_pipeline(local_pool, http, shutdown_event, browser=True))
            await asyncio.gather(*runs)
    finally:
        await close_all_pools()
        await close_redis()


async def _drain_once(*, browser: bool) -> None:
    """Run the pipeline until every ready queue is empty, then stop."""
    from src.db import close_all_pools, create_local_pool
    from src.redis_queue import close_redis, get_inflight_depth, get_queue_depths
    from src.shared.http import create_http_client
    from src.workers.pipeline import run_pipeline

    local_pool = await create_local_pool()
    shutdown_event = asyncio.Event()
    wtypes = ["simple", "browser"] if browser else ["simple"]

    try:
        async with create_http_client() as http:
            tasks = [
                asyncio.create_task(run_pipeline(local_pool, http, shutdown_event, browser=w == "browser"))
                for w in wtypes
            ]
            while not all(t.done() for t in tasks):
                await asyncio.sleep(5)
                depths = await get_queue_depths()
                ready = sum(
                    v for k, v in depths.items()
                    if k.endswith(":total") and any(k.startswith(f"ready:{w}:") for w in wtypes)
                )
                inflight = 0
                for w in wtypes:
                    inflight += await get_inflight_depth(browser=w == "browser")
                if ready == 0 and inflight == 0:
                    shutdown_event.set()
                    break
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await close_all_pools()
        await close_redis()


# ---------------------------------------------------------------------------
# `myjobs` app
# ---------------------------------------------------------------------------

app = typer.Typer(help="myjobs: a continuously updated feed of the latest jobs", no_args_is_help=True)


@app.command()
def sync(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Sync data/companies.csv + data/boards.csv → Postgres + Redis queues."""
    from src.sync import run_sync
    asyncio.run(run_sync(dry_run=dry_run))


@app.command()
def worker(
    browser: bool = typer.Option(True, "--browser/--no-browser", help="Also process boards that need Playwright"),
    sync_first: bool = typer.Option(True, "--sync/--no-sync", help="Sync CSV config before starting"),
) -> None:
    """Crawl continuously; every board is re-checked on its own interval."""
    asyncio.run(_run_worker(browser=browser, sync_first=sync_first))


@app.command()
def crawl(
    browser: bool = typer.Option(False, "--browser/--no-browser", help="Also drain browser queues"),
) -> None:
    """One pass: drain the ready queues, then exit (dev / cron use)."""
    asyncio.run(_drain_once(browser=browser))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8080),
) -> None:
    """Serve the public feed API and web page."""
    import uvicorn
    uvicorn.run("src.api.app:app", host=host, port=port, proxy_headers=True)


@app.command()
def stats() -> None:
    """Feed freshness and coverage at a glance."""
    async def _fetch():
        from src.api.queries import fetch_stats
        from src.db import close_all_pools, create_local_pool
        pool = await create_local_pool()
        try:
            return await fetch_stats(pool)
        finally:
            await close_all_pools()

    s = asyncio.run(_fetch())
    table = Table(title="myjobs feed", box=box.SIMPLE, show_header=False)
    for key, value in s.items():
        if isinstance(value, list):
            continue
        table.add_row(key.replace("_", " "), str(value))
    console.print(table)


@app.command()
def health() -> None:
    """Crawler health checks; exits 1 when an alert fires (for cron)."""
    from src.health import evaluate, fetch_snapshot

    async def _fetch():
        from src.db import close_all_pools, create_local_pool
        pool = await create_local_pool()
        try:
            return await fetch_snapshot(pool)
        finally:
            await close_all_pools()

    snap = asyncio.run(_fetch())
    alerts = evaluate(snap)
    age = f"{snap.feed_age_minutes:.0f} min" if snap.feed_age_minutes is not None else "n/a"
    console.print(f"newest posting: {age} · active boards: {snap.active_boards} · "
                  f"overdue: {snap.overdue_boards} · gone in 24h: {snap.gone_last_day}")
    for a in alerts:
        console.print(f"[red]ALERT[/red] {a.check}: {a.message}")
    if alerts:
        raise typer.Exit(code=1)
    console.print("[green]healthy[/green]")


@app.command()
def boards(
    term: str = typer.Argument(help="Company slug or name, ATS type (e.g. greenhouse), or board slug"),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """When each matching board was last checked, when it's due, and its last error."""
    from datetime import UTC, datetime

    from src.health import fetch_boards

    async def _fetch():
        from src.db import close_all_pools, create_local_pool
        pool = await create_local_pool()
        try:
            return await fetch_boards(pool, term, limit)
        finally:
            await close_all_pools()

    def ago(ts) -> str:
        if ts is None:
            return "never"
        mins = (datetime.now(UTC) - ts).total_seconds() / 60
        if mins < 0:
            return f"in {-mins:.0f} min" if mins > -120 else f"in {-mins / 60:.0f} h"
        return f"{mins:.0f} min ago" if mins < 120 else f"{mins / 60:.0f} h ago"

    rows = asyncio.run(_fetch())
    if not rows:
        console.print(f"No boards match {term!r}.")
        raise typer.Exit(code=1)
    table = Table(box=box.SIMPLE)
    for col in ("board", "ats", "status", "last success", "next check", "fails", "jobs", "last error"):
        table.add_column(col)
    for r in rows:
        status = r["board_status"] if r["is_enabled"] else "disabled"
        table.add_row(r["board_slug"], r["crawler_type"], status, ago(r["last_success_at"]), ago(r["next_check_at"]),
                      str(r["consecutive_failures"]), str(r["active_jobs"]), r["last_error"] or "")
    console.print(table)


@app.command(name="apply-tech-gate")
def apply_tech_gate() -> None:
    """Apply the tech-only rule (D27) to stored postings; rerun after changing tech_gate.py."""
    async def _run():
        from src.db import close_all_pools, create_local_pool
        from src.processing.tech_backfill import apply_tech_gate as run
        pool = await create_local_pool()
        try:
            return await run(pool)
        finally:
            await close_all_pools()

    counts = asyncio.run(_run())
    console.print(", ".join(f"{k}: {v}" for k, v in counts.items()))


@app.command(name="prune-scrape-queues")
def prune_scrape_queues() -> None:
    """Remove stale per-domain scrape queues from Redis."""
    from src.redis_queue import close_redis, prune_stale_scrape_queues

    async def _prune():
        await prune_stale_scrape_queues()
        await close_redis()

    asyncio.run(_prune())
    console.print("[green]Pruned stale scrape queues.[/green]")


company_app = typer.Typer(help="Manage the company list")
app.add_typer(company_app, name="company")


@company_app.command("add")
def company_add(
    name: str = typer.Option(...),
    slug: str = typer.Option(...),
    ats: str  = typer.Option(..., help="greenhouse | lever | ashby | workday | smartrecruiters"),
    tier: int = typer.Option(2, help="1=top, 2=mid, 3=other"),
    industry: str = typer.Option("tech"),
    website: str = typer.Option(""),
    workday_host: str = typer.Option(""),
    workday_board: str = typer.Option(""),
) -> None:
    """Add a company + board to companies.csv and boards.csv."""
    industry_code = _INDUSTRY_CODES.get(industry.lower(), 1)
    new_company = {
        "slug": slug, "name": name, "website": website,
        "industry": industry_code, "tier": tier, "enabled": "true",
    }

    monitor_type, scraper_type = _ATS_TO_MONITOR.get(ats, ("", ""))
    if not monitor_type:
        console.print(f"[yellow]Unknown ATS '{ats}' — adding company without a board row.[/yellow]")
        board_row = None
    elif ats == "workday":
        if not workday_host or not workday_board:
            console.print("[red]--workday-host and --workday-board required for workday.[/red]")
            raise typer.Exit(1)
        m = re.search(r"\.(wd\d+)\.", workday_host)
        wi = m.group(1) if m else "wd1"
        board_row = {
            "company_slug": slug,
            "board_slug": f"{slug}-workday",
            "board_url": f"https://{workday_host}/{workday_board}",
            "monitor_type": "workday",
            "monitor_config": json.dumps({"company": slug, "wd_instance": wi, "site": workday_board}),
            "scraper_type": "workday",
            "scraper_config": "",
        }
    else:
        board_row = {
            "company_slug": slug,
            "board_slug": f"{slug}-{ats}",
            "board_url": _board_url_for(ats, slug),
            "monitor_type": monitor_type,
            "monitor_config": json.dumps({"token": slug}),
            "scraper_type": scraper_type,
            "scraper_config": "",
        }

    companies = _read_csv(_COMPANIES_CSV)
    for i, r in enumerate(companies):
        if r["slug"] == slug:
            companies[i] = new_company
            break
    else:
        companies.append(new_company)
    _write_csv(_COMPANIES_CSV, _COMPANY_FIELDS, companies)

    if board_row:
        boards = _read_csv(_BOARDS_CSV)
        boards = [b for b in boards if b.get("board_slug") != board_row["board_slug"]]
        boards.append(board_row)
        _write_csv(_BOARDS_CSV, _BOARD_FIELDS, boards)

    console.print(f"[green]Added {name} ({ats}/{slug}, tier {tier})[/green]")
    if board_row:
        console.print(f"[dim]Board: {board_row['board_url']}[/dim]")
    console.print("[dim]Run [bold]myjobs sync[/bold] to push changes to Postgres + Redis.[/dim]")


@company_app.command("list")
def company_list(
    top: int = typer.Option(50),
) -> None:
    """List companies from data/companies.csv."""
    companies = _read_csv(_COMPANIES_CSV)
    enabled = [c for c in companies if c.get("enabled", "true").lower() != "false"][:top]
    if not enabled:
        console.print("[yellow]No companies in data/companies.csv.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Companies — {len(enabled)} enabled", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Name",    min_width=22)
    table.add_column("Slug",    width=18)
    table.add_column("Tier",    width=5)
    table.add_column("Industry",width=5)
    for c in enabled:
        table.add_row(c["name"][:22], c["slug"][:18], c.get("tier", "2"), c.get("industry", ""))
    console.print(table)


@company_app.command("disable")
def company_disable(slug: str = typer.Argument()) -> None:
    """Set enabled=false for a company in data/companies.csv."""
    companies = _read_csv(_COMPANIES_CSV)
    found = False
    for r in companies:
        if r["slug"] == slug:
            r["enabled"] = "false"
            found = True
            break
    if not found:
        console.print(f"[red]Slug '{slug}' not found in data/companies.csv.[/red]")
        raise typer.Exit(1)
    _write_csv(_COMPANIES_CSV, _COMPANY_FIELDS, companies)
    console.print(f"[yellow]Disabled {slug}. Run [bold]myjobs sync[/bold] to propagate.[/yellow]")


def myjobs_main() -> None:
    app()


if __name__ == "__main__":
    app()
