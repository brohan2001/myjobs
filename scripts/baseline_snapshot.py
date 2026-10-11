"""Read-only baseline snapshot of the crawl database.

Writes ``docs/baseline/<YYYY-MM-DD>.json`` and ``.md`` summarising companies,
boards per crawler type, active postings, recent success and recent runs.

Live mode (Postgres, SELECT only)::

    python scripts/baseline_snapshot.py [--dsn postgresql://...]

Legacy mode (old SQLite ``jobs.db``, opened ``mode=ro``)::

    python scripts/baseline_snapshot.py --legacy-sqlite /path/to/jobs.db

Nothing here writes to a database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.logger import get_logger  # noqa: E402

log = get_logger(__name__)

TOP_COMPANIES = 50
RECENT_HOURS = 48
RECENT_RUNS = 5

# ---------------------------------------------------------------------------
# SQL (SELECT only). Keys are the logical query names used by build_report.
# ---------------------------------------------------------------------------

PG_QUERIES: dict[str, str] = {
    "companies_total": "SELECT count(*) AS n FROM company",
    "companies_active": ("SELECT count(DISTINCT company_id) AS n FROM job_posting WHERE is_active"),
    "boards_by_type": (
        "SELECT COALESCE(crawler_type, '(none)') AS crawler_type,"
        " count(*) AS total,"
        " count(*) FILTER (WHERE is_enabled AND board_status NOT IN ('disabled','gone')) AS enabled,"
        " count(*) FILTER (WHERE consecutive_failures > 0) AS failing,"
        " count(*) FILTER (WHERE NOT is_enabled OR board_status IN ('disabled','gone')) AS disabled"
        " FROM job_board GROUP BY 1 ORDER BY total DESC, crawler_type"
    ),
    "postings_by_type": (
        "SELECT COALESCE(b.crawler_type, '(none)') AS crawler_type, count(*) AS active_postings"
        " FROM job_posting p LEFT JOIN job_board b ON b.id = p.board_id"
        " WHERE p.is_active GROUP BY 1 ORDER BY active_postings DESC, crawler_type"
    ),
    "top_companies": (
        "SELECT c.slug AS company, c.name AS name, count(*) AS active_postings"
        " FROM job_posting p JOIN company c ON c.id = p.company_id"
        " WHERE p.is_active GROUP BY c.slug, c.name"
        f" ORDER BY active_postings DESC, c.slug LIMIT {TOP_COMPANIES}"
    ),
    "recent_success": (
        "SELECT count(*) AS n FROM job_board"
        f" WHERE last_success_at >= now() - interval '{RECENT_HOURS} hours'"
    ),
    "recent_runs": (
        "SELECT run_date, started_at, finished_at, jobs_scraped, jobs_new,"
        " jobs_shortlisted, error AS errors FROM daily_runs"
        f" ORDER BY run_date DESC LIMIT {RECENT_RUNS}"
    ),
}

SQLITE_QUERIES: dict[str, str] = {
    "companies_total": "SELECT count(*) AS n FROM companies",
    "companies_active": (
        "SELECT count(DISTINCT company_id) AS n FROM jobs WHERE company_id IS NOT NULL"
    ),
    "boards_by_type": (
        "SELECT COALESCE(monitor_type, '(none)') AS crawler_type,"
        " count(*) AS total,"
        " sum(CASE WHEN is_enabled = 1 THEN 1 ELSE 0 END) AS enabled,"
        " sum(CASE WHEN consecutive_failures > 0 THEN 1 ELSE 0 END) AS failing,"
        " sum(CASE WHEN is_enabled = 1 THEN 0 ELSE 1 END) AS disabled"
        " FROM boards GROUP BY 1 ORDER BY total DESC, crawler_type"
    ),
    "postings_by_type": (
        "SELECT COALESCE(ats_type, '(none)') AS crawler_type, count(*) AS active_postings"
        " FROM jobs GROUP BY 1 ORDER BY active_postings DESC, crawler_type"
    ),
    "top_companies": (
        "SELECT c.slug AS company, c.name AS name, count(*) AS active_postings"
        " FROM jobs j JOIN companies c ON c.id = j.company_id"
        " GROUP BY c.slug, c.name"
        f" ORDER BY active_postings DESC, c.slug LIMIT {TOP_COMPANIES}"
    ),
    "recent_success": ("SELECT last_success_at AS ts FROM boards WHERE last_success_at IS NOT NULL"),
    "recent_runs": (
        "SELECT run_date, started_at, finished_at, jobs_scraped, jobs_new,"
        " jobs_shortlisted, errors FROM daily_runs"
        f" ORDER BY run_date DESC LIMIT {RECENT_RUNS}"
    ),
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parse_ts(value: Any) -> datetime | None:
    """Parse datetime / ISO / SQLite timestamp strings; naive values stay naive."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def run_duration(started: Any, finished: Any) -> tuple[float | None, bool]:
    """Return ``(duration_seconds, tz_suspect)`` without correcting anything.

    ``tz_suspect`` is True when the duration is negative, or when exactly one
    side is timezone-aware (so subtraction is unreliable).
    """
    s, f = _parse_ts(started), _parse_ts(finished)
    if s is None or f is None:
        return None, False
    if (s.tzinfo is None) != (f.tzinfo is None):
        return None, True
    secs = (f - s).total_seconds()
    return secs, secs < 0


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def build_report(rows: dict[str, list[dict]], *, source: str, now: datetime | None = None) -> dict:
    """Assemble the report dict from raw query rows (same shape for both sources)."""
    now = now or datetime.now(timezone.utc)

    boards = []
    for r in rows["boards_by_type"]:
        total, failing = int(r["total"] or 0), int(r["failing"] or 0)
        boards.append(
            {
                "crawler_type": r["crawler_type"],
                "total": total,
                "enabled": int(r["enabled"] or 0),
                "failing": failing,
                "disabled": int(r["disabled"] or 0),
                "failure_pct": _pct(failing, total),
            }
        )

    # recent_success: PG returns a count; SQLite returns timestamps filtered here.
    rs = rows["recent_success"]
    if rs and "n" in rs[0]:
        recent = int(rs[0]["n"] or 0)
    else:
        cutoff = now - timedelta(hours=RECENT_HOURS)
        recent = 0
        for r in rs:
            ts = _parse_ts(r["ts"])
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                recent += 1

    runs = []
    for r in rows["recent_runs"]:
        secs, suspect = run_duration(r.get("started_at"), r.get("finished_at"))
        runs.append(
            {
                "run_date": _iso(r.get("run_date")),
                "started_at": _iso(r.get("started_at")),
                "finished_at": _iso(r.get("finished_at")),
                "duration_seconds": secs,
                "tz_suspect": suspect,
                "jobs_scraped": r.get("jobs_scraped"),
                "jobs_new": r.get("jobs_new"),
                "jobs_shortlisted": r.get("jobs_shortlisted"),
                "errors": r.get("errors"),
            }
        )

    return {
        "source": source,
        "generated_at": now.isoformat(),
        "companies": {
            "total": int(rows["companies_total"][0]["n"]),
            "with_active_postings": int(rows["companies_active"][0]["n"]),
        },
        "boards_by_crawler_type": boards,
        "boards_totals": {
            k: sum(b[k] for b in boards) for k in ("total", "enabled", "failing", "disabled")
        },
        "active_postings_by_crawler_type": [
            {"crawler_type": r["crawler_type"], "active_postings": int(r["active_postings"])}
            for r in rows["postings_by_type"]
        ],
        "top_companies_by_active_postings": [
            {
                "company": r["company"],
                "name": r["name"],
                "active_postings": int(r["active_postings"]),
            }
            for r in rows["top_companies"]
        ],
        "boards_success_last_48h": recent,
        "latest_daily_runs": runs,
    }


def render_markdown(rep: dict) -> str:
    c, t = rep["companies"], rep["boards_totals"]
    out = [
        f"# Baseline snapshot ({rep['source']})",
        "",
        f"Generated: {rep['generated_at']}",
        "",
        "## Companies",
        f"- Total: {c['total']}",
        f"- With >=1 active posting: {c['with_active_postings']}",
        "",
        "## Boards per crawler type",
        "",
        "| crawler_type | total | enabled | failing | disabled | failure % |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for b in rep["boards_by_crawler_type"]:
        out.append(
            f"| {b['crawler_type']} | {b['total']} | {b['enabled']} | {b['failing']}"
            f" | {b['disabled']} | {b['failure_pct']} |"
        )
    out += [
        f"| **all** | {t['total']} | {t['enabled']} | {t['failing']} | {t['disabled']}"
        f" | {_pct(t['failing'], t['total'])} |",
        "",
        f"Boards with a successful run in the last {RECENT_HOURS}h: {rep['boards_success_last_48h']}",
        "",
        "## Active postings per crawler type",
        "",
        "| crawler_type | active postings |",
        "|---|---:|",
    ]
    for r in rep["active_postings_by_crawler_type"]:
        out.append(f"| {r['crawler_type']} | {r['active_postings']} |")
    out += [
        "",
        f"## Top {TOP_COMPANIES} companies by active postings",
        "",
        "| # | company | active postings |",
        "|---:|---|---:|",
    ]
    for i, r in enumerate(rep["top_companies_by_active_postings"], 1):
        out.append(f"| {i} | {r['name'] or r['company']} | {r['active_postings']} |")
    out += [
        "",
        f"## Latest {RECENT_RUNS} daily runs",
        "",
        "| run_date | started | finished | duration s | tz_suspect | scraped | new | shortlisted |",
        "|---|---|---|---:|---|---:|---:|---:|",
    ]
    for r in rep["latest_daily_runs"]:
        out.append(
            f"| {r['run_date']} | {r['started_at']} | {r['finished_at']} | {r['duration_seconds']}"
            f" | {str(r['tz_suspect']).lower()} | {r['jobs_scraped']} | {r['jobs_new']}"
            f" | {r['jobs_shortlisted']} |"
        )
    out.append("")
    return "\n".join(out)


def write_report(rep: dict, out_dir: Path, stem: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    jp.write_text(json.dumps(rep, indent=2, default=str) + "\n")
    mp.write_text(render_markdown(rep))
    return jp, mp


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


async def collect_pg(conn: Any) -> dict[str, list[dict]]:
    """Run every query on an asyncpg-like connection (``await conn.fetch(sql)``)."""
    rows: dict[str, list[dict]] = {}
    for name, sql in PG_QUERIES.items():
        rows[name] = [dict(r) for r in await conn.fetch(sql)]
    return rows


def collect_sqlite(path: str) -> dict[str, list[dict]]:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return {
            name: [dict(r) for r in conn.execute(sql).fetchall()]
            for name, sql in SQLITE_QUERIES.items()
        }
    finally:
        conn.close()


async def _run_live(dsn: str) -> dict:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        # Belt and braces: the session itself refuses writes.
        await conn.execute("SET default_transaction_read_only = on")
        rows = await collect_pg(conn)
    finally:
        await conn.close()
    return build_report(rows, source="postgres")


def main(argv: list[str] | None = None, *, today: Callable[[], date] = date.today) -> int:
    ap = argparse.ArgumentParser(description="Read-only baseline snapshot of the crawl DB")
    ap.add_argument("--dsn", help="Postgres DSN (default: settings.local_database_url)")
    ap.add_argument("--legacy-sqlite", metavar="PATH", help="read the old jobs.db read-only")
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "baseline"))
    ap.add_argument("--stem", help="output file stem (default: YYYY-MM-DD[-legacy])")
    args = ap.parse_args(argv)

    if args.legacy_sqlite:
        rep = build_report(collect_sqlite(args.legacy_sqlite), source="legacy_sqlite")
        stem = args.stem or f"{today().isoformat()}-legacy"
    else:
        dsn = args.dsn
        if not dsn:
            from src.config import settings

            dsn = settings.local_database_url
        rep = asyncio.run(_run_live(dsn))
        stem = args.stem or today().isoformat()

    jp, mp = write_report(rep, Path(args.out_dir), stem)
    log.info("baseline written json=%s md=%s source=%s", jp, mp, rep["source"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
