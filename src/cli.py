from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.config import OUTPUT_DIR, load_companies
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
    scrape_only: bool = typer.Option(False, "--scrape-only", help="Skip rendering the report"),
) -> None:
    """Run the full daily pipeline: scrape → parse → rank → shortlist → report."""
    from src.pipeline import run_daily
    asyncio.run(run_daily(shortlist_limit=top))


# ── show ──────────────────────────────────────────────────────────────────────

@app.command()
def show(
    top: int = typer.Option(20, help="Number of jobs to display"),
    date_: Optional[str] = typer.Option(None, "--date", help="Run date (YYYY-MM-DD). Defaults to today."),
    role: Optional[str] = typer.Option(None, help="Filter by role category"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum total score"),
) -> None:
    """Show shortlisted jobs in a terminal table."""
    run_date = date_ or date.today().isoformat()
    init_db()

    with get_conn() as conn:
        rows = get_shortlist(conn, run_date, limit=200)

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
    table.add_column("Title",    min_width=30)
    table.add_column("Company",  width=18, no_wrap=True)
    table.add_column("Role",     width=10, no_wrap=True)
    table.add_column("Visa",     width=11, no_wrap=True)
    table.add_column("Posted",   width=10, no_wrap=True)
    table.add_column("Link",     min_width=20)

    for i, row in enumerate(rows, 1):
        score = f"{row['total_score']:.1f}"
        visa = {1: "[green]CONFIRMED[/]", 0: "[yellow]UNKNOWN[/]", -1: "[red]NO[/]"}.get(
            row["visa_signal"], "?"
        )
        table.add_row(
            str(i),
            score,
            row["title"][:50],
            (row["company_name"] or "")[:18],
            (row["role_category"] or "other").upper()[:10],
            visa,
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


@company_app.command("add")
def company_add(
    name: str = typer.Option(..., help="Company display name"),
    slug: str = typer.Option(..., help="ATS slug (e.g. 'stripe')"),
    ats: str  = typer.Option(..., help="ATS type: greenhouse | lever"),
    tier: int = typer.Option(2, help="Tier: 1=top, 2=mid, 3=other"),
    industry: str = typer.Option("tech", help="Industry: tech | fintech | enterprise"),
) -> None:
    """Add a company to the target list."""
    init_db()
    with get_conn() as conn:
        upsert_company(conn, {
            "name": name, "slug": slug, "ats_type": ats,
            "domain": None, "industry": industry, "tier": tier,
        })
    console.print(f"[green]Added {name} ({ats}/{slug}, tier {tier})[/green]")


@company_app.command("list")
def company_list() -> None:
    """List all active companies."""
    init_db()
    with get_conn() as conn:
        rows = get_all_active_companies(conn)

    table = Table(title="Target Companies", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Name",     min_width=20)
    table.add_column("Slug",     width=16)
    table.add_column("ATS",      width=12)
    table.add_column("Tier",     width=5)
    table.add_column("Industry", width=12)
    table.add_column("Last Scraped", width=16)

    for r in rows:
        table.add_row(
            r["name"], r["slug"], r["ats_type"], str(r["tier"]),
            r["industry"] or "—",
            (r["last_scraped"] or "never")[:16],
        )
    console.print(table)


@company_app.command("disable")
def company_disable(
    slug: str = typer.Argument(help="Company slug to disable"),
) -> None:
    """Disable a company (stop scraping it)."""
    init_db()
    with get_conn() as conn:
        conn.execute("UPDATE companies SET active=0 WHERE slug=?", (slug,))
    console.print(f"[yellow]Disabled {slug}[/yellow]")


if __name__ == "__main__":
    app()
