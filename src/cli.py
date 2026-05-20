from __future__ import annotations

import asyncio
import csv
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.scoring_config import OUTPUT_DIR

console = Console()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"
_COMPANIES_CSV = _DATA_DIR / "companies.csv"
_BOARDS_CSV    = _DATA_DIR / "boards.csv"
_COMPANY_FIELDS = ["slug", "name", "website", "industry", "tier", "enabled", "h1b_petitions_recent"]
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
# Pipeline helpers (used by both `myjobs run` and `crawler run`)
# ---------------------------------------------------------------------------


async def _run_pipeline_once(browser: bool = False) -> None:
    """Run the pipeline until all ready queues drain to zero."""
    import httpx
    from src.db import create_local_pool
    from src.redis_queue import get_queue_depths, get_inflight_depth, close_redis
    from src.workers.pipeline import run_pipeline

    local_pool = await create_local_pool()
    shutdown_event = asyncio.Event()
    wtype = "browser" if browser else "simple"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
        pipeline_task = asyncio.create_task(
            run_pipeline(local_pool, http, shutdown_event, browser=browser)
        )

        # Poll until all ready queues for this wtype have drained
        while not pipeline_task.done():
            await asyncio.sleep(5)
            depths = await get_queue_depths()
            inflight = await get_inflight_depth(browser=browser)
            ready_total = sum(
                v for k, v in depths.items()
                if k.startswith(f"ready:{wtype}:") and k.endswith(":total")
            )
            if ready_total == 0 and inflight == 0:
                shutdown_event.set()
                break

        try:
            await asyncio.wait_for(pipeline_task, timeout=60.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pipeline_task.cancel()

    await close_redis()


async def _full_daily_run(shortlist_top: int = 50) -> None:
    """Sync → pipeline → score → report → log."""
    from datetime import datetime
    from src.db import create_local_pool, close_all_pools
    from src.sync import run_sync
    from src.ranker import run_scoring
    from src.renderer import fetch_shortlist, render_report

    run_date = date.today().isoformat()
    started_at = datetime.now()

    console.print(f"[bold blue]myjobs run — {run_date}[/bold blue]")
    console.print("[dim]Step 1/4: Syncing CSV → Postgres + Redis...[/dim]")
    await run_sync()

    console.print("[dim]Step 2/4: Running monitor pipeline...[/dim]")
    await _run_pipeline_once(browser=False)

    local_pool = await create_local_pool()
    try:
        console.print("[dim]Step 3/4: Scoring + shortlisting...[/dim]")
        shortlisted = await run_scoring(local_pool, shortlist_top=shortlist_top)
        console.print(f"[green]Shortlisted {shortlisted} jobs.[/green]")

        console.print("[dim]Step 4/4: Rendering report...[/dim]")
        job_rows = await fetch_shortlist(local_pool, limit=shortlist_top)
        jobs_scraped = await local_pool.fetchval(
            "SELECT COUNT(*) FROM job_posting WHERE is_active = true"
        )
        elapsed_s = (datetime.now() - started_at).total_seconds()
        report = render_report(job_rows, run_date, {
            "jobs_scraped": jobs_scraped,
            "jobs_new": jobs_scraped,
            "shortlisted": shortlisted,
            "elapsed_s": elapsed_s,
        })
        console.print(f"[green]Report: {report}[/green]")

        finished_at = datetime.now()
        await local_pool.execute("""
            INSERT INTO daily_runs (run_date, started_at, finished_at, jobs_scraped, jobs_shortlisted)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (run_date) DO UPDATE SET
                finished_at = EXCLUDED.finished_at,
                jobs_scraped = EXCLUDED.jobs_scraped,
                jobs_shortlisted = EXCLUDED.jobs_shortlisted
        """, run_date, started_at, finished_at, int(jobs_scraped or 0), shortlisted)

    finally:
        await close_all_pools()


# ---------------------------------------------------------------------------
# `myjobs` app
# ---------------------------------------------------------------------------

app = typer.Typer(help="myjobs — daily job scraper and ranker", no_args_is_help=True)


@app.command()
def run(
    top: int = typer.Option(50, help="Number of jobs to shortlist"),
) -> None:
    """Full daily run: sync → monitor → score → shortlist → report."""
    asyncio.run(_full_daily_run(shortlist_top=top))


@app.command()
def show(
    top: int = typer.Option(20, help="Number of jobs to display"),
    role: Optional[str] = typer.Option(None, help="Filter by role category"),
    min_score: float = typer.Option(0.0, "--min-score"),
    us_only: bool = typer.Option(False, "--us-only"),
    new_grad: bool = typer.Option(False, "--new-grad"),
) -> None:
    """Show shortlisted jobs in a terminal table."""
    async def _fetch():
        from src.db import create_local_pool, close_all_pools
        from src.renderer import fetch_shortlist
        pool = await create_local_pool()
        try:
            return await fetch_shortlist(pool, limit=200)
        finally:
            await close_all_pools()

    rows = asyncio.run(_fetch())

    if role:
        rows = [r for r in rows if (r.get("role_category") or "").lower() == role.lower()]
    if min_score:
        rows = [r for r in rows if r.get("total_score", 0) >= min_score]
    if us_only:
        rows = [r for r in rows if _is_us(r.get("location", ""))]
    if new_grad:
        rows = [r for r in rows if r.get("early_career") or r.get("experience_max") is None]
    rows = rows[:top]

    if not rows:
        console.print("[yellow]No shortlisted jobs found.[/yellow]")
        raise typer.Exit()

    table = Table(
        title=f"Top {len(rows)} Shortlisted Jobs",
        box=box.ROUNDED, show_lines=False, header_style="bold cyan",
    )
    table.add_column("#",       width=3,  no_wrap=True)
    table.add_column("Score",   width=6,  no_wrap=True)
    table.add_column("Title",   min_width=28)
    table.add_column("Company", width=18, no_wrap=True)
    table.add_column("Role",    width=10, no_wrap=True)
    table.add_column("Visa",    width=11, no_wrap=True)
    table.add_column("Salary",  width=14, no_wrap=True)
    table.add_column("Posted",  width=10, no_wrap=True)
    table.add_column("Link",    min_width=20)

    for i, row in enumerate(rows, 1):
        score = f"{row.get('total_score', 0):.1f}"
        visa = {1: "[green]CONFIRMED[/]", 0: "[yellow]UNKNOWN[/]", -1: "[red]NO[/]"}.get(
            row.get("visa_signal", 0), "?"
        )
        sal_min = row.get("salary_min")
        sal_max = row.get("salary_max")
        sal_str = f"${sal_min//1000}k" if sal_min else "—"
        if sal_min and sal_max:
            sal_str += f"–${sal_max//1000}k"
        table.add_row(
            str(i), score,
            (row.get("title") or "")[:46],
            (row.get("company_name") or "")[:18],
            (row.get("role_category") or "other").upper()[:10],
            visa, sal_str,
            str(row.get("posted_date") or "—"),
            row.get("url") or "",
        )
    console.print(table)


def _is_us(location: str) -> bool:
    if not location:
        return True
    loc_l = location.lower()
    non_us = {"india", "canada", "united kingdom", "ireland", "germany", "australia",
               "singapore", "poland", "netherlands", "france", "spain", "brazil"}
    return not any(s in loc_l for s in non_us)


@app.command(name="open-report")
def open_report(
    date_: Optional[str] = typer.Option(None, "--date"),
) -> None:
    """Open today's HTML report in the browser."""
    run_date = date_ or date.today().isoformat()
    report = OUTPUT_DIR / run_date / "report.html"
    if not report.exists():
        console.print(f"[red]Report not found: {report}[/red]")
        raise typer.Exit(1)
    subprocess.run(["open", str(report)], check=False)
    console.print(f"[green]Opened {report}[/green]")


@app.command()
def apply(
    job_id: str = typer.Argument(help="Job ID (UUID) from the database"),
    notes: Optional[str] = typer.Option(None),
) -> None:
    """Mark a job as applied (manual)."""
    async def _apply():
        from src.db import create_local_pool, close_all_pools
        pool = await create_local_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT jp.id, jp.titles[1] AS title, c.name AS company_name "
                    "FROM job_posting jp JOIN company c ON c.id = jp.company_id "
                    "WHERE jp.id = $1::uuid", job_id
                )
                if not row:
                    console.print(f"[red]Job {job_id} not found.[/red]")
                    raise typer.Exit(1)
                await conn.execute(
                    "UPDATE job_posting SET status = 'applied', applied_at = now() WHERE id = $1::uuid",
                    job_id,
                )
                console.print(
                    f"[green]Marked applied: {row['title']} @ {row['company_name']}[/green]"
                )
        finally:
            await close_all_pools()

    asyncio.run(_apply())


@app.command()
def history(
    days: int = typer.Option(30, help="Look-back window in days"),
) -> None:
    """Show recently applied jobs."""
    async def _fetch():
        from src.db import create_local_pool, close_all_pools
        pool = await create_local_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetch("""
                    SELECT jp.id::text, jp.titles[1] AS title, jp.source_url AS url,
                           jp.applied_at, c.name AS company_name
                    FROM job_posting jp
                    JOIN company c ON c.id = jp.company_id
                    WHERE jp.status = 'applied'
                      AND jp.applied_at >= now() - ($1 || ' days')::interval
                    ORDER BY jp.applied_at DESC
                """, str(days))
        finally:
            await close_all_pools()

    rows = asyncio.run(_fetch())
    if not rows:
        console.print(f"[yellow]No applications in the last {days} days.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Applications (last {days}d)", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Applied",  width=12)
    table.add_column("Company",  width=18)
    table.add_column("Title",    min_width=30)
    for r in rows:
        table.add_row(
            str(r["applied_at"])[:10],
            (r["company_name"] or "")[:18],
            (r["title"] or "")[:50],
        )
    console.print(table)


@app.command()
def stats() -> None:
    """Show aggregate statistics."""
    async def _fetch():
        from src.db import create_local_pool, close_all_pools
        pool = await create_local_pool()
        try:
            async with pool.acquire() as conn:
                total_jobs  = await conn.fetchval("SELECT COUNT(*) FROM job_posting WHERE is_active = true")
                total_applied = await conn.fetchval(
                    "SELECT COUNT(*) FROM job_posting WHERE status = 'applied'"
                )
                total_runs  = await conn.fetchval("SELECT COUNT(*) FROM daily_runs")
                top_companies = await conn.fetch("""
                    SELECT c.name, COUNT(jp.id) AS cnt
                    FROM job_posting jp JOIN company c ON c.id = jp.company_id
                    WHERE jp.status = 'shortlisted'
                    GROUP BY c.name ORDER BY cnt DESC LIMIT 5
                """)
                return total_jobs, total_applied, total_runs, top_companies
        finally:
            await close_all_pools()

    total_jobs, total_applied, total_runs, top_companies = asyncio.run(_fetch())
    console.print("\n[bold]Stats[/bold]")
    console.print(f"  Active jobs in DB  : [cyan]{total_jobs}[/cyan]")
    console.print(f"  Applications sent  : [green]{total_applied}[/green]")
    console.print(f"  Daily runs logged  : [blue]{total_runs}[/blue]")
    if top_companies:
        console.print("\n  [bold]Most shortlisted companies:[/bold]")
        for r in top_companies:
            console.print(f"    {r['name']:25s} {r['cnt']}")


@app.command()
def serve(
    port: int = typer.Option(8080),
    host: str = typer.Option("127.0.0.1"),
) -> None:
    """Start the live job board web server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install uvicorn[/red]")
        raise typer.Exit(1)
    console.print(f"[bold green]myjobs live → http://{host}:{port}[/bold green]")
    uvicorn.run("src.server:app", host=host, port=port, reload=False, log_level="warning")


@app.command()
def generate(
    top: int = typer.Option(10, help="Number of top jobs to process"),
    days: int = typer.Option(1, help="Look back N days (0 = all time)"),
    out: Optional[str] = typer.Option(None, help="Override output directory"),
) -> None:
    """Generate tailored resume bullets + cover letters via Claude API."""
    from src.ai.generator import generate_for_shortlist

    async def _fetch_jobs():
        from src.db import create_local_pool, close_all_pools
        from src.renderer import fetch_shortlist
        pool = await create_local_pool()
        try:
            return await fetch_shortlist(pool, limit=days * 200 if days > 0 else 5000)
        finally:
            await close_all_pools()

    jobs = asyncio.run(_fetch_jobs())
    if not jobs:
        console.print("[yellow]No shortlisted jobs found. Run [bold]myjobs run[/bold] first.[/yellow]")
        raise typer.Exit()

    console.print(f"[dim]Found {len(jobs)} shortlisted jobs. Generating materials for top {top}...[/dim]")
    try:
        results = asyncio.run(generate_for_shortlist(jobs, top_n=top))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    today = date.today().isoformat()
    out_dir = Path(out) if out else OUTPUT_DIR / today / "applications"
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle_path = out_dir / "materials.json"
    with open(bundle_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    for r in results:
        if r.get("error"):
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", f"{r['company_name']}_{r['title']}".lower())[:60]
        md_path = out_dir / f"{slug}.md"
        with open(md_path, "w") as f:
            f.write(f"# {r['company_name']} — {r['title']}\n\n")
            f.write(f"**Score:** {r.get('total_score', 0):.1f}  |  **Role:** {r.get('role_category')}  |  [Job link]({r.get('url', '')})\n\n")
            f.write("## Tailored Resume Bullets\n\n")
            for bullet in r.get("resume_bullets", []):
                f.write(f"- {bullet}\n")
            f.write("\n## Cover Letter\n\n")
            f.write(r.get("cover_letter", ""))
            f.write("\n")

    success = [r for r in results if not r.get("error")]
    console.print(f"\n[green]Generated {len(success)}/{len(results)} successfully.[/green]")
    console.print(f"[dim]Output: {out_dir}/[/dim]")


@app.command(name="verify-api")
def verify_api() -> None:
    """Smoke-test the Anthropic API key."""
    from src.scoring_config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        console.print("[red]ANTHROPIC_API_KEY not set. Add it to .env[/red]")
        raise typer.Exit(1)
    try:
        import anthropic
    except ImportError:
        console.print("[red]anthropic not installed. Run: pip install -e .[/red]")
        raise typer.Exit(1)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
        )
    except anthropic.AuthenticationError:
        console.print("[red]Authentication failed — API key invalid.[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]API call failed: {exc}[/red]")
        raise typer.Exit(1)
    reply = msg.content[0].text.strip()
    console.print(f"[green]API key valid.[/green] Response: [bold]{reply}[/bold]")


@app.command(name="update-h1b")
def update_h1b() -> None:
    """Update H1-B petition counts in the company table from data/h1b_sponsors.json."""
    from src.scoring_config import load_h1b_sponsors

    h1b_data = load_h1b_sponsors()
    if not h1b_data:
        console.print("[yellow]data/h1b_sponsors.json not found or empty.[/yellow]")
        raise typer.Exit(1)

    async def _update():
        from src.db import create_local_pool, close_all_pools
        pool = await create_local_pool()
        try:
            async with pool.acquire() as conn:
                companies = await conn.fetch("SELECT id, name, slug FROM company")
                updated = 0
                for c in companies:
                    key = re.sub(
                        r"\b(inc|llc|corp|ltd|technologies|systems|networks|labs|software|"
                        r"services|solutions|group|holdings|global|international|enterprises)\b\.?",
                        "",
                        c["name"].lower().strip(),
                    ).strip()
                    key = re.sub(r"\s+", " ", key)
                    entry = h1b_data.get(key) or h1b_data.get(c["slug"])
                    if entry:
                        total = entry.get("total", 0)
                        # Store in extras JSONB since company table doesn't have h1b column
                        await conn.execute(
                            "UPDATE company SET extras = COALESCE(extras, '{}'::jsonb) || $1::jsonb "
                            "WHERE id = $2",
                            json.dumps({"h1b_petitions_recent": total}),
                            c["id"],
                        )
                        updated += 1
                return updated
        finally:
            await close_all_pools()

    updated = asyncio.run(_update())
    console.print(f"[green]Updated H1-B data for {updated} companies.[/green]")


# ── company subcommand ────────────────────────────────────────────────────────

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
        "h1b_petitions_recent": "",
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
    console.print("[dim]Run [bold]crawler sync[/bold] to push changes to Postgres + Redis.[/dim]")


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
    console.print(f"[yellow]Disabled {slug}. Run [bold]crawler sync[/bold] to propagate.[/yellow]")


# ---------------------------------------------------------------------------
# `crawler` app (jobseek-style)
# ---------------------------------------------------------------------------

crawler = typer.Typer(help="crawler — jobseek-compatible pipeline commands", no_args_is_help=True)


@crawler.command(name="run")
def crawler_run() -> None:
    """Run the simple (non-browser) discovery pipeline until all queues drain."""
    asyncio.run(_run_pipeline_once(browser=False))


@crawler.command(name="run-browser")
def crawler_run_browser() -> None:
    """Run the browser discovery pipeline until all queues drain."""
    asyncio.run(_run_pipeline_once(browser=True))


@crawler.command(name="sync")
def crawler_sync(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Sync data/companies.csv + data/boards.csv → Postgres + Redis."""
    from src.sync import run_sync
    asyncio.run(run_sync(dry_run=dry_run))


@crawler.command(name="board")
def crawler_board(
    slug: str = typer.Argument(help="Board slug to test"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Test a single board (monitor only, no DB write unless --no-dry-run)."""
    try:
        from src.workspace.cli import run_board_test
        asyncio.run(run_board_test(slug, dry_run=dry_run, verbose=verbose))
    except ImportError:
        console.print("[yellow]workspace CLI not available. Use crawler sync + run instead.[/yellow]")
        raise typer.Exit(1)


@crawler.command(name="prune-scrape-queues")
def prune_scrape_queues() -> None:
    """Remove stale per-domain scrape queues from Redis."""
    from src.redis_queue import prune_stale_scrape_queues, close_redis
    asyncio.run(prune_stale_scrape_queues())
    asyncio.run(close_redis())
    console.print("[green]Pruned stale scrape queues.[/green]")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def myjobs_main() -> None:
    app()


def crawler_main() -> None:
    crawler()


if __name__ == "__main__":
    app()
