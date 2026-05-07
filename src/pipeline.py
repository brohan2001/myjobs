from __future__ import annotations

import asyncio
import random
import time
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.config import load_companies
from src.database import (
    create_daily_run,
    get_conn,
    get_existing_keys,
    get_jobs_for_rerank,
    get_new_jobs,
    get_shortlist,
    get_top_unshortlisted,
    init_db,
    insert_jobs,
    log_run_error,
    mark_shortlisted,
    update_company_scraped,
    update_daily_run,
    update_job_scores,
    update_job_signals,
    upsert_company,
)
from src.ranker import parse_signals, score_job
from src.renderer import render_report
from src.scrapers.base import ScraperError
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.amazon import AmazonScraper
from src.scrapers.linkedin import LinkedInScraper

console = Console()

# Max concurrent scrape tasks per ATS batch
_SCRAPE_CONCURRENCY = asyncio.Semaphore(5)


async def _scrape_company(scraper, company: dict, company_id: int, existing_keys: set) -> tuple[int, int, str | None]:
    """Returns (scraped_count, new_count, error_str | None)."""
    async with _SCRAPE_CONCURRENCY:
        try:
            jobs = await scraper.fetch_jobs(company, company_id)
            new_jobs = scraper.deduplicate(jobs, existing_keys)
            with get_conn() as conn:
                inserted = insert_jobs(conn, new_jobs)
                update_company_scraped(conn, company["slug"], company["ats_type"])
            for j in new_jobs:
                existing_keys.add((j["external_id"], j["ats_type"]))
            return len(jobs), inserted, None
        except ScraperError as e:
            return 0, 0, f"{company['ats_type']}/{company['slug']}: {e}"
        except Exception as e:
            return 0, 0, f"{company['ats_type']}/{company['slug']}: unexpected: {e}"


async def _scrape_linkedin_company(scraper, company: dict, company_id: int, existing_keys: set) -> tuple[int, int, str | None]:
    """LinkedIn runs without the shared semaphore — it enforces its own rate limit."""
    try:
        jobs = await scraper.fetch_jobs(company, company_id)
        new_jobs = scraper.deduplicate(jobs, existing_keys)
        with get_conn() as conn:
            inserted = insert_jobs(conn, new_jobs)
            update_company_scraped(conn, company["slug"], company["ats_type"])
        for j in new_jobs:
            existing_keys.add((j["external_id"], j["ats_type"]))
        return len(jobs), inserted, None
    except Exception as e:
        return 0, 0, f"linkedin/{company['slug']}: {e}"


async def run_daily(shortlist_limit: int = 50) -> Path:
    run_date = date.today().isoformat()
    start_time = time.monotonic()
    errors: list[str] = []

    console.rule(f"[bold blue]Job Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── 1. INIT ────────────────────────────────────────────────────────────
    init_db()
    with get_conn() as conn:
        create_daily_run(conn, run_date)

    companies = load_companies()
    gh_companies = [c for c in companies if c["ats_type"] == "greenhouse"]
    lv_companies = [c for c in companies if c["ats_type"] == "lever"]
    wd_companies = [c for c in companies if c["ats_type"] == "workday"]
    az_companies = [c for c in companies if c["ats_type"] == "amazon"]
    li_companies = [c for c in companies if c["ats_type"] == "linkedin"]

    console.print(
        f"[dim]Companies: {len(gh_companies)} Greenhouse, {len(lv_companies)} Lever, "
        f"{len(wd_companies)} Workday, {len(az_companies)} Amazon, {len(li_companies)} LinkedIn[/dim]"
    )

    with get_conn() as conn:
        existing_keys: set[tuple] = get_existing_keys(conn)
        company_id_map: dict[str, int] = {}
        for c in companies:
            cid = upsert_company(conn, c)
            company_id_map[f"{c['ats_type']}:{c['slug']}"] = cid

    # ── 2. SCRAPE ──────────────────────────────────────────────────────────
    jobs_scraped = 0
    jobs_new = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        total_companies = len(gh_companies) + len(lv_companies) + len(wd_companies) + len(az_companies)
        task_gh = progress.add_task("[cyan]Greenhouse", total=len(gh_companies))
        task_lv = progress.add_task("[yellow]Lever     ", total=len(lv_companies))
        task_wd = progress.add_task("[green]Workday   ", total=len(wd_companies))
        task_az = progress.add_task("[orange3]Amazon    ", total=max(len(az_companies), 1))

        # Greenhouse
        async with GreenhouseScraper() as gh_scraper:
            gh_tasks = [
                _scrape_company(gh_scraper, c, company_id_map[f"greenhouse:{c['slug']}"], existing_keys)
                for c in gh_companies
            ]
            for coro in asyncio.as_completed(gh_tasks):
                scraped, new, err = await coro
                jobs_scraped += scraped
                jobs_new += new
                if err:
                    errors.append(err)
                progress.advance(task_gh)

        # Lever
        async with LeverScraper() as lv_scraper:
            lv_tasks = [
                _scrape_company(lv_scraper, c, company_id_map[f"lever:{c['slug']}"], existing_keys)
                for c in lv_companies
            ]
            for coro in asyncio.as_completed(lv_tasks):
                scraped, new, err = await coro
                jobs_scraped += scraped
                jobs_new += new
                if err:
                    errors.append(err)
                progress.advance(task_lv)

        # Workday
        if wd_companies:
            async with WorkdayScraper() as wd_scraper:
                wd_tasks = [
                    _scrape_company(wd_scraper, c, company_id_map[f"workday:{c['slug']}"], existing_keys)
                    for c in wd_companies
                ]
                for coro in asyncio.as_completed(wd_tasks):
                    scraped, new, err = await coro
                    jobs_scraped += scraped
                    jobs_new += new
                    if err:
                        errors.append(err)
                    progress.advance(task_wd)

        # Amazon
        if az_companies:
            async with AmazonScraper() as az_scraper:
                for c in az_companies:
                    cid = company_id_map[f"amazon:{c['slug']}"]
                    scraped, new, err = await _scrape_company(az_scraper, c, cid, existing_keys)
                    jobs_scraped += scraped
                    jobs_new += new
                    if err:
                        errors.append(err)
                    progress.advance(task_az)

    # LinkedIn runs outside the progress bar (best-effort, sequential, rate-limited)
    if li_companies:
        task_li = progress.add_task("[blue]LinkedIn  ", total=len(li_companies)) if False else None
        console.print(f"[dim]LinkedIn: scraping {len(li_companies)} companies (rate-limited)...[/dim]")
        async with LinkedInScraper() as li_scraper:
            for c in li_companies:
                cid = company_id_map[f"linkedin:{c['slug']}"]
                scraped, new, err = await _scrape_linkedin_company(li_scraper, c, cid, existing_keys)
                jobs_scraped += scraped
                jobs_new += new
                if err:
                    errors.append(err)
                # Random delay between companies to avoid rate limiting
                await asyncio.sleep(random.uniform(5, 10))

    console.print(f"[green]Scraped {jobs_scraped} jobs ({jobs_new} new)[/green]")

    # ── 3. PARSE SIGNALS ───────────────────────────────────────────────────
    with get_conn() as conn:
        new_jobs = get_new_jobs(conn)
        console.print(f"[dim]Parsing signals for {len(new_jobs)} new jobs...[/dim]")
        for job in new_jobs:
            signals = parse_signals(dict(job))
            update_job_signals(conn, job["id"], signals)

    # ── 4. RANK ────────────────────────────────────────────────────────────
    with get_conn() as conn:
        jobs_to_rank = get_jobs_for_rerank(conn)
        console.print(f"[dim]Scoring {len(jobs_to_rank)} jobs...[/dim]")
        for job in jobs_to_rank:
            scores = score_job(dict(job))
            update_job_scores(conn, job["id"], scores)

    # ── 5. SHORTLIST ───────────────────────────────────────────────────────
    with get_conn() as conn:
        top_jobs = get_top_unshortlisted(conn, limit=shortlist_limit)
        if top_jobs:
            mark_shortlisted(conn, [j["id"] for j in top_jobs])
        shortlisted_count = len(top_jobs)

    console.print(f"[green]Shortlisted {shortlisted_count} jobs[/green]")

    # ── 6. RENDER ──────────────────────────────────────────────────────────
    with get_conn() as conn:
        shortlist = get_shortlist(conn, run_date, limit=shortlist_limit)

    elapsed = time.monotonic() - start_time
    report_path = render_report(list(shortlist), run_date, {
        "jobs_scraped": jobs_scraped,
        "jobs_new": jobs_new,
        "shortlisted": shortlisted_count,
        "errors": len(errors),
        "elapsed_s": elapsed,
    })
    console.print(f"[bold green]Report: {report_path}[/bold green]")

    # ── 7. FINALIZE ────────────────────────────────────────────────────────
    with get_conn() as conn:
        update_daily_run(conn, run_date, {
            "finished_at":      datetime.now().isoformat(timespec="seconds"),
            "jobs_scraped":     jobs_scraped,
            "jobs_new":         jobs_new,
            "jobs_shortlisted": shortlisted_count,
            "errors":           __import__("json").dumps(errors),
            "status":           "complete" if not errors else "complete_with_errors",
        })

    elapsed_fmt = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    console.rule("[bold blue]Done")
    console.print(f"[bold]Run complete in {elapsed_fmt}[/bold]")
    if errors:
        console.print(f"[yellow]{len(errors)} scrape error(s):[/yellow]")
        for e in errors[:10]:
            console.print(f"  [red]• {e}[/red]")

    return report_path
