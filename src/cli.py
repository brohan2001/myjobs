from __future__ import annotations

import asyncio
import csv
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.config import OUTPUT_DIR
from src.database import (
    get_all_active_companies,
    get_applications,
    get_conn,
    get_daily_run,
    get_job_by_id,
    get_shortlist,
    init_db,
    upsert_company,
)

app = typer.Typer(help="myjobs — daily job scraper and ranker", no_args_is_help=True)
console = Console()


# ── run ───────────────────────────────────────────────────────────────────────

@app.command()
def run(
    top: int = typer.Option(50, help="Number of jobs to shortlist"),
    board: Optional[str] = typer.Option(None, "--board", help="Only run a single board slug (debug mode)"),
) -> None:
    """Run the full daily pipeline: monitor → scrape → rank → shortlist → report."""
    from src.pipeline import run_daily
    asyncio.run(run_daily(shortlist_limit=top, board_slug=board))


# ── show ──────────────────────────────────────────────────────────────────────

@app.command()
def show(
    top: int = typer.Option(20, help="Number of jobs to display"),
    date_: Optional[str] = typer.Option(None, "--date", help="Run date (YYYY-MM-DD). Defaults to today."),
    role: Optional[str] = typer.Option(None, help="Filter by role category"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum total score"),
    us_only: bool = typer.Option(False, "--us-only", help="Show only US/remote positions"),
    new_grad: bool = typer.Option(False, "--new-grad", help="Show only entry-level/new grad jobs"),
) -> None:
    """Show shortlisted jobs in a terminal table."""
    run_date = date_ or date.today().isoformat()
    init_db()

    with get_conn() as conn:
        rows = get_shortlist(conn, run_date, limit=200, us_only=us_only, new_grad_only=new_grad)

    if role:
        rows = [r for r in rows if (r["role_category"] or "").lower() == role.lower()]
    if min_score:
        rows = [r for r in rows if r["total_score"] >= min_score]
    rows = rows[:top]

    if not rows:
        console.print(f"[yellow]No shortlisted jobs found for {run_date}.[/yellow]")
        raise typer.Exit()

    table = Table(
        title=f"Top {len(rows)} Jobs — {run_date}",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("#",        width=3,  no_wrap=True)
    table.add_column("Score",    width=6,  no_wrap=True)
    table.add_column("Title",    min_width=28)
    table.add_column("Company",  width=18, no_wrap=True)
    table.add_column("Role",     width=10, no_wrap=True)
    table.add_column("Visa",     width=11, no_wrap=True)
    table.add_column("Salary",   width=14, no_wrap=True)
    table.add_column("Posted",   width=10, no_wrap=True)
    table.add_column("Link",     min_width=20)

    for i, row in enumerate(rows, 1):
        score = f"{row['total_score']:.1f}"
        visa = {1: "[green]CONFIRMED[/]", 0: "[yellow]UNKNOWN[/]", -1: "[red]NO[/]"}.get(
            row["visa_signal"], "?"
        )
        sal_min = row["salary_min_usd"] if "salary_min_usd" in row.keys() else None
        sal_max = row["salary_max_usd"] if "salary_max_usd" in row.keys() else None
        if sal_min:
            sal_str = f"${sal_min//1000}k"
            if sal_max:
                sal_str += f"–${sal_max//1000}k"
        else:
            sal_str = "—"
        table.add_row(
            str(i),
            score,
            row["title"][:46],
            (row["company_name"] or "")[:18],
            (row["role_category"] or "other").upper()[:10],
            visa,
            sal_str,
            row["posted_date"] or "—",
            row["url"],
        )

    console.print(table)


# ── open-report ───────────────────────────────────────────────────────────────

@app.command(name="open-report")
def open_report(
    date_: Optional[str] = typer.Option(None, "--date", help="Report date (YYYY-MM-DD). Defaults to today.")
) -> None:
    """Open today's HTML report in the default browser."""
    run_date = date_ or date.today().isoformat()
    report = OUTPUT_DIR / run_date / "report.html"
    if not report.exists():
        console.print(f"[red]Report not found: {report}[/red]")
        console.print("Run [bold]myjobs run[/bold] first.")
        raise typer.Exit(1)
    subprocess.run(["open", str(report)], check=False)
    console.print(f"[green]Opened {report}[/green]")


# ── apply ─────────────────────────────────────────────────────────────────────

@app.command()
def apply(
    job_id: int = typer.Argument(help="Job ID from the database"),
    notes: Optional[str] = typer.Option(None, help="Optional notes about the application"),
) -> None:
    """Mark a job as applied (manual)."""
    init_db()
    with get_conn() as conn:
        job = get_job_by_id(conn, job_id)
        if not job:
            console.print(f"[red]Job ID {job_id} not found.[/red]")
            raise typer.Exit(1)
        conn.execute(
            "INSERT INTO applications (job_id, method, notes) VALUES (?, 'manual', ?)",
            (job_id, notes),
        )
        conn.execute("UPDATE jobs SET status='applied' WHERE id=?", (job_id,))
    console.print(f"[green]Marked job {job_id} as applied: {job['title']} @ {job['company_name']}[/green]")


# ── history ───────────────────────────────────────────────────────────────────

@app.command()
def history(
    days: int = typer.Option(30, help="Look-back window in days"),
) -> None:
    """Show application history."""
    init_db()
    with get_conn() as conn:
        rows = get_applications(conn, days)

    if not rows:
        console.print(f"[yellow]No applications in the last {days} days.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Applications (last {days}d)", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Applied",    width=12)
    table.add_column("Company",   width=18)
    table.add_column("Title",     min_width=30)
    table.add_column("Status",    width=12)

    for r in rows:
        table.add_row(
            (r["applied_at"] or "")[:10],
            (r["company_name"] or "")[:18],
            (r["title"] or "")[:50],
            r["status"] or "submitted",
        )
    console.print(table)


# ── stats ─────────────────────────────────────────────────────────────────────

@app.command()
def stats() -> None:
    """Show aggregate statistics."""
    init_db()
    with get_conn() as conn:
        total_jobs    = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        total_applied = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        total_runs    = conn.execute("SELECT COUNT(*) FROM daily_runs").fetchone()[0]
        top_companies = conn.execute(
            """SELECT c.name, COUNT(*) as cnt FROM jobs j
               JOIN companies c ON j.company_id=c.id
               WHERE j.status='shortlisted'
               GROUP BY c.name ORDER BY cnt DESC LIMIT 5"""
        ).fetchall()

    console.print(f"\n[bold]Stats[/bold]")
    console.print(f"  Total jobs in DB : [cyan]{total_jobs}[/cyan]")
    console.print(f"  Applications sent: [green]{total_applied}[/green]")
    console.print(f"  Daily runs run   : [blue]{total_runs}[/blue]")
    if top_companies:
        console.print("\n  [bold]Most shortlisted companies:[/bold]")
        for r in top_companies:
            console.print(f"    {r['name']:25s} {r['cnt']}")


# ── company ───────────────────────────────────────────────────────────────────

company_app = typer.Typer(help="Manage the company list")
app.add_typer(company_app, name="company")

_DATA_DIR = Path(__file__).parent.parent / "data"
_COMPANIES_CSV = _DATA_DIR / "companies.csv"
_BOARDS_CSV    = _DATA_DIR / "boards.csv"
_COMPANY_FIELDS = ["slug", "name", "website", "industry", "tier", "enabled", "h1b_petitions_recent"]
_BOARD_FIELDS   = ["company_slug", "board_slug", "board_url", "monitor_type", "monitor_config", "scraper_type", "scraper_config"]

_ATS_TO_MONITOR = {
    "greenhouse":     ("greenhouse", "skip"),
    "lever":          ("lever",      "skip"),
    "ashby":          ("ashby",      "skip"),
    "smartrecruiters":("smartrecruiters", "skip"),
    "workable":       ("workable",   "skip"),
    "workday":        ("workday",    "workday"),
}

_INDUSTRY_CODES = {"tech": 1, "fintech": 2, "enterprise": 1, "media": 6, "telecom": 7}


def _board_url_for(ats: str, slug: str) -> str:
    urls = {
        "greenhouse":     f"https://job-boards.greenhouse.io/{slug}",
        "lever":          f"https://jobs.lever.co/{slug}",
        "ashby":          f"https://jobs.ashbyhq.com/{slug}",
        "smartrecruiters":f"https://careers.smartrecruiters.com/{slug}",
        "workable":       f"https://apply.workable.com/{slug}/",
    }
    return urls.get(ats, "")


def _read_csv(path: Path, fields: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


@company_app.command("add")
def company_add(
    name: str = typer.Option(..., help="Company display name"),
    slug: str = typer.Option(..., help="Company slug (e.g. 'stripe')"),
    ats: str  = typer.Option(..., help="Monitor type: greenhouse | lever | ashby | workday | smartrecruiters"),
    tier: int = typer.Option(2, help="Tier: 1=top, 2=mid, 3=other"),
    industry: str = typer.Option("tech", help="Industry code: tech | fintech | enterprise | media | telecom"),
    website: str = typer.Option("", help="Company website URL"),
    workday_host: str = typer.Option("", help="Workday host (e.g. stripe.wd1.myworkdayjobs.com)"),
    workday_board: str = typer.Option("", help="Workday board/site name"),
) -> None:
    """Add a company and synthesize a board row in companies.csv and boards.csv."""
    industry_code = _INDUSTRY_CODES.get(industry.lower(), 1)
    new_company = {
        "slug": slug, "name": name, "website": website,
        "industry": industry_code, "tier": tier, "enabled": "true",
        "h1b_petitions_recent": "",
    }

    # Build board row
    monitor_type, scraper_type = _ATS_TO_MONITOR.get(ats, ("", ""))
    if not monitor_type:
        console.print(f"[yellow]Unknown ATS '{ats}' — adding company without a board row.[/yellow]")
        board_row = None
    elif ats == "workday":
        if not workday_host or not workday_board:
            console.print("[red]--workday-host and --workday-board required for workday ATS.[/red]")
            raise typer.Exit(1)
        import re as _re
        m = _re.search(r"\.(wd\d+)\.", workday_host)
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
        board_url = _board_url_for(ats, slug)
        board_row = {
            "company_slug": slug,
            "board_slug": f"{slug}-{ats}",
            "board_url": board_url,
            "monitor_type": monitor_type,
            "monitor_config": json.dumps({"token": slug}),
            "scraper_type": scraper_type,
            "scraper_config": "",
        }

    # Update companies.csv
    companies = _read_csv(_COMPANIES_CSV, _COMPANY_FIELDS)
    for i, r in enumerate(companies):
        if r["slug"] == slug:
            companies[i] = new_company
            break
    else:
        companies.append(new_company)
    _write_csv(_COMPANIES_CSV, _COMPANY_FIELDS, companies)

    # Update boards.csv
    if board_row:
        boards = _read_csv(_BOARDS_CSV, _BOARD_FIELDS)
        boards = [b for b in boards if b.get("board_slug") != board_row["board_slug"]]
        boards.append(board_row)
        _write_csv(_BOARDS_CSV, _BOARD_FIELDS, boards)

    console.print(f"[green]Added {name} ({ats}/{slug}, tier {tier})[/green]")
    if board_row:
        console.print(f"[dim]Board: {board_row['board_url']}[/dim]")
    else:
        console.print(f"[yellow]Edit data/boards.csv manually to add board config for {slug}.[/yellow]")


@company_app.command("list")
def company_list(
    enabled_only: bool = typer.Option(True, "--enabled-only/--all", help="Show only enabled companies"),
    top: int = typer.Option(50, help="Max rows to display"),
) -> None:
    """List companies from data/companies.csv."""
    from src.companies import load_companies as _load

    companies = _load(enabled_only=enabled_only)[:top]
    if not companies:
        console.print("[yellow]No companies found in data/companies.csv.[/yellow]")
        raise typer.Exit()

    table = Table(
        title=f"Companies ({'enabled' if enabled_only else 'all'}) — {len(companies)} shown",
        box=box.ROUNDED, header_style="bold cyan",
    )
    table.add_column("Name",     min_width=22)
    table.add_column("Slug",     width=18)
    table.add_column("Tier",     width=5)
    table.add_column("Industry", width=5)
    table.add_column("H1B",      width=6)
    table.add_column("Enabled",  width=8)

    for c in companies:
        table.add_row(
            c.name[:22], c.slug[:18], str(c.tier), str(c.industry),
            str(c.h1b_petitions_recent) if c.h1b_petitions_recent else "—",
            "[green]yes[/]" if c.enabled else "[red]no[/]",
        )
    console.print(table)


@company_app.command("disable")
def company_disable(
    slug: str = typer.Argument(help="Company slug to disable"),
) -> None:
    """Set enabled=false for a company in data/companies.csv."""
    companies = _read_csv(_COMPANIES_CSV, _COMPANY_FIELDS)
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
    console.print(f"[yellow]Disabled {slug} in data/companies.csv.[/yellow]")


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    port: int = typer.Option(8080, help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    days: int = typer.Option(14, help="Show jobs from the last N days"),
) -> None:
    """Start the live job board web server at http://localhost:<port>"""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install uvicorn[/red]")
        raise typer.Exit(1)

    from src.database import init_db
    init_db()
    console.print(f"[bold green]myjobs live → http://{host}:{port}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")

    import os
    os.environ.setdefault("MYJOBS_SERVE_DAYS", str(days))

    uvicorn.run(
        "src.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="warning",
    )


@app.command(name="update-h1b")
def update_h1b() -> None:
    """Populate H1-B petition counts from data/h1b_sponsors.json into the database."""
    from src.config import load_h1b_sponsors
    from src.database import populate_h1b_data
    init_db()
    h1b_data = load_h1b_sponsors()
    if not h1b_data:
        console.print("[yellow]data/h1b_sponsors.json not found or empty.[/yellow]")
        console.print("Place the file in data/ with normalized company names as keys.")
        raise typer.Exit(1)
    with get_conn() as conn:
        updated = populate_h1b_data(conn, h1b_data)
    console.print(f"[green]Updated H1-B data for {updated} companies.[/green]")


@app.command(name="verify-api")
def verify_api() -> None:
    """Smoke-test the Anthropic API key with a minimal call."""
    from src.config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        console.print("[red]ANTHROPIC_API_KEY is not set.[/red]")
        console.print("Add it to your [bold].env[/bold] file: ANTHROPIC_API_KEY=sk-ant-...")
        raise typer.Exit(1)

    try:
        import anthropic
    except ImportError:
        console.print("[red]anthropic package not installed.[/red]")
        console.print("Run: [bold]pip install -e .[/bold]")
        raise typer.Exit(1)

    console.print("[dim]Sending smoke-test request to Anthropic API...[/dim]")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
        )
    except anthropic.AuthenticationError:
        console.print("[red]Authentication failed — API key is invalid or revoked.[/red]")
        raise typer.Exit(1)
    except anthropic.BadRequestError as exc:
        if "credit balance" in str(exc).lower():
            console.print("[yellow]API key is valid but your credit balance is too low.[/yellow]")
            console.print("Add credits at [bold]console.anthropic.com → Plans & Billing[/bold].")
        else:
            console.print(f"[red]API call failed: {exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]API call failed: {exc}[/red]")
        raise typer.Exit(1)

    reply = msg.content[0].text.strip()
    usage = msg.usage
    console.print(f"[green]API key is valid.[/green] Response: [bold]{reply}[/bold]")
    console.print(f"[dim]Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}[/dim]")


# ── generate ──────────────────────────────────────────────────────────────────

@app.command()
def generate(
    top: int = typer.Option(10, help="Number of top shortlisted jobs to process"),
    days: int = typer.Option(1, help="Look back N days for shortlisted jobs (0 = all time)"),
    out: Optional[str] = typer.Option(None, help="Override output directory"),
) -> None:
    """Generate tailored resume bullets + cover letters for top shortlisted jobs via Claude API."""
    from src.ai.generator import generate_for_shortlist
    from src.database import get_shortlisted_jobs

    init_db()
    with get_conn() as conn:
        days_window = days if days > 0 else 3650
        jobs = get_shortlisted_jobs(conn, days=days_window)

    if not jobs:
        console.print(f"[yellow]No shortlisted jobs found in the last {days} day(s). Run [bold]myjobs run[/bold] first.[/yellow]")
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
            f.write(f"**Score:** {r['total_score']:.1f}  |  **Role:** {r['role_category']}  |  [Job link]({r['url']})\n\n")
            f.write("## Tailored Resume Bullets\n\n")
            for bullet in r.get("resume_bullets", []):
                f.write(f"- {bullet}\n")
            f.write("\n## Cover Letter\n\n")
            f.write(r.get("cover_letter", ""))
            f.write("\n")

    errors = [r for r in results if r.get("error")]
    success = [r for r in results if not r.get("error")]

    total_cache_read  = sum(r.get("tokens", {}).get("cache_read",  0) for r in success)
    total_cache_write = sum(r.get("tokens", {}).get("cache_write", 0) for r in success)
    total_output      = sum(r.get("tokens", {}).get("output",      0) for r in success)

    table = Table(title="Generated Application Materials", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("#",        width=3,  no_wrap=True)
    table.add_column("Company",  width=18, no_wrap=True)
    table.add_column("Title",    min_width=30)
    table.add_column("Score",    width=6,  no_wrap=True)
    table.add_column("Bullets",  width=8,  no_wrap=True)
    table.add_column("Letter",   width=7,  no_wrap=True)

    for i, r in enumerate(results, 1):
        if r.get("error"):
            table.add_row(str(i), r.get("company_name", "—")[:18], r.get("title", "")[:50], "ERR", "—", "[red]FAIL[/]")
        else:
            table.add_row(
                str(i),
                (r.get("company_name") or "")[:18],
                (r.get("title") or "")[:50],
                f"{r['total_score']:.1f}",
                str(len(r.get("resume_bullets", []))),
                "[green]yes[/]",
            )

    console.print(table)
    console.print(f"\n[green]Generated {len(success)}/{len(results)} successfully.[/green]")
    console.print(f"[dim]Output: {out_dir}/[/dim]")
    console.print(f"[dim]Tokens — cache write: {total_cache_write:,}  cache read: {total_cache_read:,}  output: {total_output:,}[/dim]")
    if errors:
        for r in errors:
            console.print(f"[red]  Failed: {r.get('company_name')} — {r.get('title')}: {r.get('error')}[/red]")


if __name__ == "__main__":
    app()
