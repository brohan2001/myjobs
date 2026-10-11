"""Unit tests for scripts/baseline_snapshot.py (no database required)."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "baseline_snapshot", Path(__file__).parents[2] / "scripts" / "baseline_snapshot.py"
)
bs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bs)


class FakeConn:
    """Minimal asyncpg stand-in: records SQL, answers from a name->rows map."""

    def __init__(self, answers):
        self.sqls: list[str] = []
        self._by_sql = {bs.PG_QUERIES[k]: v for k, v in answers.items()}

    async def fetch(self, sql):
        self.sqls.append(sql)
        return self._by_sql[sql]


PG_ANSWERS = {
    "companies_total": [{"n": 10}],
    "companies_active": [{"n": 4}],
    "boards_by_type": [
        {"crawler_type": "greenhouse", "total": 8, "enabled": 7, "failing": 2, "disabled": 1},
        {"crawler_type": "lever", "total": 0, "enabled": 0, "failing": 0, "disabled": 0},
    ],
    "postings_by_type": [{"crawler_type": "greenhouse", "active_postings": 120}],
    "top_companies": [{"company": "acme", "name": "Acme", "active_postings": 120}],
    "recent_success": [{"n": 5}],
    "recent_runs": [
        {
            "run_date": date(2026, 5, 20),
            "started_at": datetime(2026, 5, 20, 10, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 5, 20, 11, tzinfo=timezone.utc),
            "jobs_scraped": 1,
            "jobs_new": 1,
            "jobs_shortlisted": 1,
            "errors": None,
        }
    ],
}


def test_queries_are_select_only():
    for sql in list(bs.PG_QUERIES.values()) + list(bs.SQLITE_QUERIES.values()):
        assert sql.lstrip().upper().startswith("SELECT")
        for word in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER "):
            assert word not in sql.upper()


async def test_collect_pg_runs_every_query_through_fake_connection():
    conn = FakeConn(PG_ANSWERS)
    rows = await bs.collect_pg(conn)
    assert set(rows) == set(bs.PG_QUERIES)
    assert conn.sqls == list(bs.PG_QUERIES.values())


async def test_build_report_from_pg_rows_and_markdown():
    rows = await bs.collect_pg(FakeConn(PG_ANSWERS))
    now = datetime(2026, 5, 21, tzinfo=timezone.utc)
    rep = bs.build_report(rows, source="postgres", now=now)
    assert rep["companies"] == {"total": 10, "with_active_postings": 4}
    gh = rep["boards_by_crawler_type"][0]
    assert gh["failure_pct"] == 25.0
    assert rep["boards_by_crawler_type"][1]["failure_pct"] == 0.0  # no div-by-zero
    assert rep["boards_totals"] == {"total": 8, "enabled": 7, "failing": 2, "disabled": 1}
    assert rep["boards_success_last_48h"] == 5
    assert rep["latest_daily_runs"][0]["duration_seconds"] == 3600.0
    assert rep["latest_daily_runs"][0]["tz_suspect"] is False
    md = bs.render_markdown(rep)
    assert "| greenhouse | 8 | 7 | 2 | 1 | 25.0 |" in md
    json.dumps(rep, default=str)


def test_run_duration_flags_negative_and_mixed_tz_without_fixing():
    assert bs.run_duration("2026-05-20 20:57:54", "2026-05-20T17:28:43") == (-12551.0, True)
    aware = datetime(2026, 5, 20, tzinfo=timezone.utc)
    assert bs.run_duration(aware, datetime(2026, 5, 20)) == (None, True)
    assert bs.run_duration(None, aware) == (None, False)
    assert bs.run_duration(aware, aware + timedelta(seconds=5)) == (5.0, False)


def _make_legacy_db(path: Path, now: datetime):
    c = sqlite3.connect(path)
    c.executescript(
        """
        CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, slug TEXT);
        CREATE TABLE boards (id INTEGER PRIMARY KEY, company_id INT, monitor_type TEXT,
            is_enabled INT, last_success_at TEXT, consecutive_failures INT);
        CREATE TABLE jobs (id INTEGER PRIMARY KEY, company_id INT, ats_type TEXT);
        CREATE TABLE daily_runs (id INTEGER PRIMARY KEY, run_date TEXT, started_at TEXT,
            finished_at TEXT, jobs_scraped INT, jobs_new INT, jobs_shortlisted INT, errors TEXT);
        INSERT INTO companies VALUES (1,'Acme','acme'),(2,'Beta','beta'),(3,'Gamma','gamma');
        INSERT INTO jobs VALUES (1,1,'greenhouse'),(2,1,'greenhouse'),(3,2,'lever');
        INSERT INTO daily_runs VALUES (1,'2026-05-20','2026-05-20 20:00:00','2026-05-20T17:00:00',9,3,2,NULL);
        """
    )
    recent = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(days=9)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO boards VALUES (1,1,'greenhouse',1,?,0)", (recent,))
    c.execute("INSERT INTO boards VALUES (2,1,'greenhouse',1,?,3)", (old,))
    c.execute("INSERT INTO boards VALUES (3,2,'lever',0,NULL,0)")
    c.commit()
    c.close()


def test_legacy_sqlite_end_to_end(tmp_path):
    db = tmp_path / "jobs.db"
    now = datetime.now(timezone.utc)
    _make_legacy_db(db, now)
    before = db.read_bytes()

    out = tmp_path / "out"
    rc = bs.main(
        ["--legacy-sqlite", str(db), "--out-dir", str(out)], today=lambda: date(2026, 5, 20)
    )
    assert rc == 0
    rep = json.loads((out / "2026-05-20-legacy.json").read_text())
    assert (out / "2026-05-20-legacy.md").exists()
    assert rep["source"] == "legacy_sqlite"
    assert rep["companies"] == {"total": 3, "with_active_postings": 2}
    by = {b["crawler_type"]: b for b in rep["boards_by_crawler_type"]}
    assert by["greenhouse"] == {
        "crawler_type": "greenhouse", "total": 2, "enabled": 2, "failing": 1,
        "disabled": 0, "failure_pct": 50.0,
    }
    assert by["lever"]["disabled"] == 1
    assert rep["boards_success_last_48h"] == 1
    assert rep["active_postings_by_crawler_type"][0] == {
        "crawler_type": "greenhouse", "active_postings": 2
    }
    assert rep["latest_daily_runs"][0]["tz_suspect"] is True
    assert db.read_bytes() == before  # read-only


def test_collect_sqlite_refuses_writes(tmp_path):
    db = tmp_path / "jobs.db"
    _make_legacy_db(db, datetime.now(timezone.utc))
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO companies VALUES (9,'x','x')")
    conn.close()
