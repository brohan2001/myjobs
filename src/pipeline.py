"""Job discovery pipeline using vendored jobseek monitors + scrapers.

Flow per daily run:
  1. Sync data/companies.csv + data/boards.csv → SQLite companies + boards tables
  2. Start shared Playwright if any enabled board requires a browser
  3. Run monitor_one_stream for all enabled boards (concurrency=20)
  4. For URL-only boards (scraper_type != skip): run scrape_one (concurrency=10)
  5. Normalize staged raw_jobs → jobs table via normalize_to_jobs_row
  6. parse_signals → score_job → mark_shortlisted → render_report
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.companies import load_boards
from src.core.monitor import monitor_one_stream
from src.core.monitors import monitor_needs_browser
from src.core.scrape import scrape_one
from src.core.scrapers import scraper_needs_browser
from src.database import (
    create_daily_run,
    get_conn,
    get_existing_keys,
    get_jobs_for_rerank,
    get_new_jobs,
    get_shortlist,
    get_top_unshortlisted,
    get_unparsed_raw_jobs,
    get_unscraped_url_only_raw_jobs,
    init_db,
    insert_jobs,
    mark_raw_parsed,
    mark_shortlisted,
    record_raw_job,
    update_board_failure,
    update_board_success,
    update_daily_run,
    update_job_scores,
    update_job_signals,
    update_raw_job_payload,
    upsert_board,
    upsert_company_from_board,
)
from src.logger import get_logger
from src.normalize import normalize_to_jobs_row
from src.ranker import parse_signals, score_job
from src.renderer import render_report
from src.shared.http import create_http_client

console = Console()
_log = get_logger("pipeline")


async def run_daily(shortlist_limit: int = 50, board_slug: str | None = None) -> Path:
    """Run the full daily job discovery pipeline.

    When *board_slug* is given only that one board is processed — useful for
    debugging a specific company board without running all 3 000+ boards.
    """
    run_date = date.today().isoformat()
    start_time = time.monotonic()
    errors: list[str] = []

    console.rule(f"[bold blue]Job Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── 1. INIT ──────────────────────────────────────────────────────────────
    init_db()
    with get_conn() as conn:
        create_daily_run(conn, run_date)
        from src.config import load_h1b_sponsors
        from src.database import populate_h1b_data
        h1b_data = load_h1b_sponsors()
        if h1b_data:
            populate_h1b_data(conn, h1b_data)

    # ── 2. SYNC CSV → DB ─────────────────────────────────────────────────────
    csv_boards = load_boards()
    if board_slug:
        csv_boards = [b for b in csv_boards if b.board_slug == board_slug]
        if not csv_boards:
            raise ValueError(f"Board not found in boards.csv: {board_slug!r}")

    board_id_map: dict[str, int] = {}
    with get_conn() as conn:
        for board in csv_boards:
            company = board.company
            if company is None:
                continue
            cid = upsert_company_from_board(
                conn, company.slug, company.name, company.industry, company.tier
            )
            bid = upsert_board(
                conn, cid, board.board_slug, board.board_url,
                board.monitor_type, board.monitor_config,
                board.scraper_type, board.scraper_config,
            )
            board_id_map[board.board_slug] = bid

    active_boards = [b for b in csv_boards if b.board_slug in board_id_map]
    console.print(f"[dim]Synced {len(active_boards)} boards to DB[/dim]")

    # ── 3. CHECK BROWSER NEEDS ───────────────────────────────────────────────
    needs_browser = any(
        monitor_needs_browser(b.monitor_type, b.monitor_config)
        or scraper_needs_browser(b.scraper_type, b.scraper_config)
        for b in active_boards
    )

    # ── 4. MONITOR ALL BOARDS ────────────────────────────────────────────────
    monitor_sem = asyncio.Semaphore(20)
    jobs_discovered = 0
    boards_ok = 0
    boards_failed = 0

    http = create_http_client()

    async def run_monitor(board, board_id, pw=None):
        nonlocal jobs_discovered, boards_ok, boards_failed
        async with monitor_sem:
            discovered = 0
            try:
                async for batch in monitor_one_stream(
                    board.board_url, board.monitor_type, board.monitor_config, http, pw=pw
                ):
                    with get_conn() as conn:
                        if batch.jobs_by_url:
                            for url, dj in batch.jobs_by_url.items():
                                payload = dataclasses.asdict(dj)
                                payload["url"] = url
                                record_raw_job(conn, board_id, url, payload, "monitor_rich")
                                discovered += 1
                        else:
                            for url in batch.urls:
                                record_raw_job(conn, board_id, url, {"url": url}, "monitor")
                                discovered += 1
                with get_conn() as conn:
                    update_board_success(conn, board_id)
                jobs_discovered += discovered
                boards_ok += 1
            except Exception as e:
                err = f"{board.board_slug}: {e}"
                _log.error("monitor.failure", extra={"board": board.board_slug, "error": str(e)})
                with get_conn() as conn:
                    update_board_failure(conn, board_id, str(e))
                errors.append(err)
                boards_failed += 1

    monitor_tasks = [run_monitor(b, board_id_map[b.board_slug]) for b in active_boards]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task_mon = progress.add_task("[cyan]Monitoring boards", total=len(active_boards))

        if needs_browser:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                monitor_tasks = [run_monitor(b, board_id_map[b.board_slug], pw=pw) for b in active_boards]
                for coro in asyncio.as_completed(monitor_tasks):
                    await coro
                    progress.advance(task_mon)
        else:
            for coro in asyncio.as_completed(monitor_tasks):
                await coro
                progress.advance(task_mon)

    await http.aclose()

    console.print(
        f"[green]Monitored {boards_ok}/{len(active_boards)} boards — "
        f"{jobs_discovered} total discoveries ({boards_failed} failures)[/green]"
    )

    # ── 5. SCRAPE URL-ONLY BOARDS ────────────────────────────────────────────
    scrape_sem = asyncio.Semaphore(10)
    scraped_count = 0
    scrape_errors = 0

    with get_conn() as conn:
        url_only_rows = get_unscraped_url_only_raw_jobs(conn, limit=5000)

    if url_only_rows:
        http2 = create_http_client()

        async def run_scrape(row, pw=None):
            nonlocal scraped_count, scrape_errors
            url = row["source_url"]
            scraper_type = row["scraper_type"]
            sc = json.loads(row["scraper_config"] or "{}")
            raw_id = row["id"]
            async with scrape_sem:
                try:
                    content = await scrape_one(url, scraper_type, sc, http2, pw=pw)
                    payload = dataclasses.asdict(content)
                    payload["url"] = url
                    with get_conn() as conn:
                        update_raw_job_payload(conn, raw_id, payload, "scraper")
                    scraped_count += 1
                except Exception as e:
                    _log.warning("scrape.failure", extra={"url": url, "error": str(e)})
                    with get_conn() as conn:
                        mark_raw_parsed(conn, raw_id, None, str(e))
                    scrape_errors += 1

        needs_browser_scrape = any(
            scraper_needs_browser(r["scraper_type"], json.loads(r["scraper_config"] or "{}"))
            for r in url_only_rows
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_sc = progress.add_task("[yellow]Scraping job pages", total=len(url_only_rows))
            scrape_tasks = [run_scrape(r) for r in url_only_rows]

            if needs_browser_scrape:
                from playwright.async_api import async_playwright
                async with async_playwright() as pw:
                    scrape_tasks = [run_scrape(r, pw=pw) for r in url_only_rows]
                    for coro in asyncio.as_completed(scrape_tasks):
                        await coro
                        progress.advance(task_sc)
            else:
                for coro in asyncio.as_completed(scrape_tasks):
                    await coro
                    progress.advance(task_sc)

        await http2.aclose()
        console.print(
            f"[dim]Scraped {scraped_count}/{len(url_only_rows)} URL-only jobs "
            f"({scrape_errors} errors)[/dim]"
        )

    # ── 6. PARSE RAW → JOBS ──────────────────────────────────────────────────
    jobs_new = 0
    parse_errors = 0

    with get_conn() as conn:
        existing_keys: set[tuple] = get_existing_keys(conn)
        raw_rows = get_unparsed_raw_jobs(conn, limit=10000)

    with get_conn() as conn:
        for row in raw_rows:
            raw_id = row["id"]
            try:
                payload = json.loads(row["payload"])
                norm = normalize_to_jobs_row(payload, row)
                key = (norm["external_id"], norm["ats_type"])
                if key in existing_keys:
                    mark_raw_parsed(conn, raw_id, None, None)
                    continue
                inserted, ids = insert_jobs(conn, [norm])
                if inserted:
                    existing_keys.add(key)
                    jobs_new += 1
                mark_raw_parsed(conn, raw_id, ids[0] if ids else None, None)
            except Exception as e:
                _log.warning("parse.failure", extra={"raw_id": raw_id, "error": str(e)})
                mark_raw_parsed(conn, raw_id, None, str(e))
                parse_errors += 1

    console.print(f"[green]{jobs_new} new jobs inserted ({parse_errors} parse errors)[/green]")

    # ── 7. PARSE SIGNALS ─────────────────────────────────────────────────────
    with get_conn() as conn:
        new_jobs = get_new_jobs(conn)
        console.print(f"[dim]Parsing signals for {len(new_jobs)} new jobs...[/dim]")
        for job in new_jobs:
            signals = parse_signals(dict(job))
            update_job_signals(conn, job["id"], signals)

    # ── 8. RANK ──────────────────────────────────────────────────────────────
    with get_conn() as conn:
        jobs_to_rank = get_jobs_for_rerank(conn)
        console.print(f"[dim]Scoring {len(jobs_to_rank)} jobs...[/dim]")
        for job in jobs_to_rank:
            scores = score_job(dict(job))
            update_job_scores(conn, job["id"], scores)

    # ── 9. SHORTLIST ─────────────────────────────────────────────────────────
    with get_conn() as conn:
        top_jobs = get_top_unshortlisted(conn, limit=shortlist_limit)
        if top_jobs:
            mark_shortlisted(conn, [j["id"] for j in top_jobs])
        shortlisted_count = len(top_jobs)

    console.print(f"[green]Shortlisted {shortlisted_count} jobs[/green]")

    # ── 10. RENDER ───────────────────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    with get_conn() as conn:
        shortlist = get_shortlist(conn, run_date, limit=shortlist_limit)

    report_path = render_report(list(shortlist), run_date, {
        "jobs_scraped": jobs_discovered,
        "jobs_new": jobs_new,
        "shortlisted": shortlisted_count,
        "errors": len(errors),
        "elapsed_s": elapsed,
    })
    console.print(f"[bold green]Report: {report_path}[/bold green]")

    # ── 11. FINALIZE ─────────────────────────────────────────────────────────
    with get_conn() as conn:
        update_daily_run(conn, run_date, {
            "finished_at":      datetime.now().isoformat(timespec="seconds"),
            "jobs_scraped":     jobs_discovered,
            "jobs_new":         jobs_new,
            "jobs_shortlisted": shortlisted_count,
            "errors":           json.dumps(errors[:50]),
            "status":           "complete" if not errors else "complete_with_errors",
        })

    elapsed_fmt = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    console.rule("[bold blue]Done")
    console.print(f"[bold]Run complete in {elapsed_fmt}[/bold]")
    if errors:
        console.print(f"[yellow]{len(errors)} monitor error(s):[/yellow]")
        for e in errors[:10]:
            console.print(f"  [red]• {e}[/red]")

    return report_path
