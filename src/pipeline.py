from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.config import load_companies
from src.logger import get_logger, log_scrape_failure
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
from src.scrapers.workday import WorkdayScraper, fetch_workday_description
from src.scrapers.amazon import AmazonScraper
from src.scrapers.google import GoogleScraper
from src.scrapers.apple import AppleScraper
from src.scrapers.linkedin import LinkedInBroadScraper, LinkedInScraper

console = Console()
_log = get_logger("pipeline")

# Max concurrent scrape tasks per ATS batch
_SCRAPE_CONCURRENCY = asyncio.Semaphore(5)


async def _scrape_company(scraper, company: dict, company_id: int, existing_keys: set) -> tuple[int, int, list[int], str | None]:
    """Returns (scraped_count, new_count, inserted_ids, error_str | None)."""
    async with _SCRAPE_CONCURRENCY:
        try:
            jobs = await scraper.fetch_jobs(company, company_id)
            new_jobs = scraper.deduplicate(jobs, existing_keys)
            with get_conn() as conn:
                inserted, inserted_ids = insert_jobs(conn, new_jobs)
                update_company_scraped(conn, company["slug"], company["ats_type"])
            for j in new_jobs:
                existing_keys.add((j["external_id"], j["ats_type"]))
            return len(jobs), inserted, inserted_ids, None
        except ScraperError as e:
            err = f"{company['ats_type']}/{company['slug']}: {e}"
            log_scrape_failure(_log, company["slug"], company["ats_type"], str(e))
            return 0, 0, [], err
        except Exception as e:
            err = f"{company['ats_type']}/{company['slug']}: unexpected: {e}"
            log_scrape_failure(_log, company["slug"], company["ats_type"], f"unexpected: {e}")
            return 0, 0, [], err


async def _scrape_linkedin_company(scraper, company: dict, company_id: int, existing_keys: set) -> tuple[int, int, str | None]:
    """LinkedIn runs without the shared semaphore — it enforces its own rate limit."""
    try:
        jobs = await scraper.fetch_jobs(company, company_id)
        new_jobs = scraper.deduplicate(jobs, existing_keys)
        with get_conn() as conn:
            inserted, _ = insert_jobs(conn, new_jobs)
            update_company_scraped(conn, company["slug"], company["ats_type"])
        for j in new_jobs:
            existing_keys.add((j["external_id"], j["ats_type"]))
        return len(jobs), inserted, None
    except Exception as e:
        log_scrape_failure(_log, company["slug"], "linkedin", str(e))
        return 0, 0, f"linkedin/{company['slug']}: {e}"


_BROAD_SEARCH_TERMS = [
    "software engineer new grad",
    "software engineer entry level",
]


async def _run_broad_linkedin_search(
    existing_keys: set,
    company_name_to_id: dict[str, int],
) -> int:
    """Broad LinkedIn keyword search across all US companies. Returns count of new jobs inserted."""
    total_new = 0
    async with LinkedInBroadScraper() as scraper:
        for term in _BROAD_SEARCH_TERMS:
            jobs = await scraper.search(
                term,
                max_results=100,
                company_name_to_id=company_name_to_id,
            )
            # Handle unknown companies: create minimal entries
            with get_conn() as conn:
                for job in jobs:
                    if job.get("company_id") is None:
                        dyn_name = job.pop("_company_name", "") or "Unknown"
                        if not dyn_name or dyn_name == "Unknown":
                            continue
                        dyn_slug = re.sub(r"[^a-z0-9-]", "-", dyn_name.lower())[:40]
                        cid = upsert_company(conn, {
                            "name": dyn_name,
                            "slug": dyn_slug,
                            "ats_type": "linkedin",
                            "domain": None,
                            "industry": "tech",
                            "tier": 3,
                        })
                        job["company_id"] = cid
                        company_name_to_id[dyn_name.lower()] = cid
                new_jobs = scraper.deduplicate(jobs, existing_keys)
                inserted, _ = insert_jobs(conn, new_jobs)
                for j in new_jobs:
                    existing_keys.add((j["external_id"], j["ats_type"]))
                total_new += inserted
            await asyncio.sleep(random.uniform(15, 25))
    return total_new


async def _enrich_workday_descriptions(job_ids: list[int]) -> None:
    """Fetch Workday detail pages for newly inserted jobs. Runs in parallel with concurrency=5."""
    if not job_ids:
        return

    with get_conn() as conn:
        placeholders = ",".join("?" * len(job_ids))
        rows = conn.execute(
            f"SELECT id, url FROM jobs WHERE id IN ({placeholders}) AND (description IS NULL OR description='')",
            job_ids,
        ).fetchall()

    if not rows:
        return

    sem = asyncio.Semaphore(5)

    async def fetch_one(job_id: int, url: str) -> tuple[int, str]:
        async with sem:
            desc = await fetch_workday_description(url)
            return job_id, desc

    tasks = [fetch_one(r["id"], r["url"]) for r in rows[:100]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    with get_conn() as conn:
        for result in results:
            if isinstance(result, tuple):
                jid, desc = result
                if desc:
                    conn.execute("UPDATE jobs SET description=? WHERE id=?", (desc, jid))


async def run_daily(shortlist_limit: int = 50) -> Path:
    run_date = date.today().isoformat()
    start_time = time.monotonic()
    errors: list[str] = []

    console.rule(f"[bold blue]Job Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── 1. INIT ────────────────────────────────────────────────────────────
    init_db()
    with get_conn() as conn:
        create_daily_run(conn, run_date)
        from src.config import load_h1b_sponsors
        from src.database import populate_h1b_data
        h1b_data = load_h1b_sponsors()
        if h1b_data:
            populate_h1b_data(conn, h1b_data)

    companies = load_companies()
    gh_companies = [c for c in companies if c["ats_type"] == "greenhouse"]
    lv_companies = [c for c in companies if c["ats_type"] == "lever"]
    wd_companies = [c for c in companies if c["ats_type"] == "workday"]
    az_companies = [c for c in companies if c["ats_type"] == "amazon"]
    li_companies = [c for c in companies if c["ats_type"] == "linkedin"]
    go_companies = [c for c in companies if c["ats_type"] == "google"]
    ap_companies = [c for c in companies if c["ats_type"] == "apple"]

    console.print(
        f"[dim]Companies: {len(gh_companies)} Greenhouse, {len(lv_companies)} Lever, "
        f"{len(wd_companies)} Workday, {len(az_companies)} Amazon, {len(li_companies)} LinkedIn, "
        f"{len(go_companies)} Google, {len(ap_companies)} Apple[/dim]"
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
    new_workday_ids: list[int] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task_gh = progress.add_task("[cyan]Greenhouse", total=max(len(gh_companies), 1))
        task_lv = progress.add_task("[yellow]Lever     ", total=max(len(lv_companies), 1))
        task_wd = progress.add_task("[green]Workday   ", total=max(len(wd_companies), 1))
        task_az = progress.add_task("[orange3]Amazon    ", total=max(len(az_companies), 1))
        task_go = progress.add_task("[red]Google    ", total=max(len(go_companies), 1))
        task_ap = progress.add_task("[white]Apple     ", total=max(len(ap_companies), 1))

        # Greenhouse
        async with GreenhouseScraper() as gh_scraper:
            gh_tasks = [
                _scrape_company(gh_scraper, c, company_id_map[f"greenhouse:{c['slug']}"], existing_keys)
                for c in gh_companies
            ]
            for coro in asyncio.as_completed(gh_tasks):
                scraped, new, _, err = await coro
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
                scraped, new, _, err = await coro
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
                    scraped, new, ids, err = await coro
                    jobs_scraped += scraped
                    jobs_new += new
                    new_workday_ids.extend(ids)
                    if err:
                        errors.append(err)
                    progress.advance(task_wd)

        # Amazon
        if az_companies:
            async with AmazonScraper() as az_scraper:
                for c in az_companies:
                    cid = company_id_map[f"amazon:{c['slug']}"]
                    scraped, new, _, err = await _scrape_company(az_scraper, c, cid, existing_keys)
                    jobs_scraped += scraped
                    jobs_new += new
                    if err:
                        errors.append(err)
                    progress.advance(task_az)

        # Google
        if go_companies:
            async with GoogleScraper() as go_scraper:
                for c in go_companies:
                    cid = company_id_map[f"google:{c['slug']}"]
                    scraped, new, _, err = await _scrape_company(go_scraper, c, cid, existing_keys)
                    jobs_scraped += scraped
                    jobs_new += new
                    if err:
                        errors.append(err)
                    progress.advance(task_go)

        # Apple
        if ap_companies:
            async with AppleScraper() as ap_scraper:
                for c in ap_companies:
                    cid = company_id_map[f"apple:{c['slug']}"]
                    scraped, new, _, err = await _scrape_company(ap_scraper, c, cid, existing_keys)
                    jobs_scraped += scraped
                    jobs_new += new
                    if err:
                        errors.append(err)
                    progress.advance(task_ap)

    # LinkedIn runs outside the progress bar (best-effort, sequential, rate-limited)
    if li_companies:
        console.print(f"[dim]LinkedIn: scraping {len(li_companies)} companies (rate-limited)...[/dim]")
        async with LinkedInScraper() as li_scraper:
            for c in li_companies:
                cid = company_id_map[f"linkedin:{c['slug']}"]
                scraped, new, err = await _scrape_linkedin_company(li_scraper, c, cid, existing_keys)
                jobs_scraped += scraped
                jobs_new += new
                if err:
                    errors.append(err)
                await asyncio.sleep(random.uniform(5, 10))

    # Broad LinkedIn keyword search (best-effort, may be rate-limited)
    console.print("[dim]LinkedIn broad search (software engineer new grad/entry level)...[/dim]")
    try:
        company_name_to_id = {
            c["name"].lower(): company_id_map.get(f"{c['ats_type']}:{c['slug']}", -1)
            for c in companies
        }
        broad_new = await _run_broad_linkedin_search(existing_keys, company_name_to_id)
        jobs_new += broad_new
        jobs_scraped += broad_new
        if broad_new:
            console.print(f"[dim]LinkedIn broad search: {broad_new} new jobs[/dim]")
    except Exception as e:
        errors.append(f"linkedin_broad: {e}")
        _log.error("linkedin_broad_failure", extra={"error": str(e)})
        console.print(f"[yellow]LinkedIn broad search failed (non-fatal): {e}[/yellow]")

    console.print(f"[green]Scraped {jobs_scraped} jobs ({jobs_new} new)[/green]")

    # ── 2b. ENRICH WORKDAY DESCRIPTIONS ───────────────────────────────────
    if new_workday_ids:
        console.print(f"[dim]Enriching descriptions for {min(len(new_workday_ids), 100)} Workday jobs...[/dim]")
        try:
            await _enrich_workday_descriptions(new_workday_ids)
        except Exception as e:
            errors.append(f"workday_enrich: {e}")
            _log.error("workday_enrich_failure", extra={"error": str(e)})
            console.print(f"[yellow]Workday description enrichment failed (non-fatal): {e}[/yellow]")

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
