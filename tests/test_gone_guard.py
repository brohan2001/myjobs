"""Delisting guards read their state from the DB and give way to a board that has steadily shrunk (D44)."""

import json
from datetime import UTC, datetime, timedelta

import structlog

from src.processing.board import _mark_gone_with_guards, _steady_shrink
from src.queries.monitor import _COUNT_BOARD_ACTIVE_AND_MISSING, _FETCH_GUARD_STATE, _MARK_GONE_BY_TIMESTAMP

LOG = structlog.get_logger()
NOW = datetime(2026, 11, 3, tzinfo=UTC)


class FakeConn:
    """A board with *active* rows, *missing* of them unseen this check, and guard state in its DB row."""

    def __init__(self, active, missing, **state):
        self.state = {k: json.dumps(v) if k != "suspect_since" else v for k, v in state.items()}
        self.counts = {"active": active, "missing": missing}
        self.writes, self.gone_calls = [], 0

    async def fetchrow(self, sql, *args):
        if sql == _FETCH_GUARD_STATE:
            return {k: self.state.get(k) for k in ("history", "streak", "suspect_counts", "suspect_since")}
        assert sql == _COUNT_BOARD_ACTIVE_AND_MISSING
        return self.counts

    async def fetch(self, sql, *args):
        assert sql == _MARK_GONE_BY_TIMESTAMP
        self.gone_calls += 1
        return [{"id": i} for i in range(self.counts["missing"])]

    async def execute(self, sql, board_id, payload):
        self.writes.append(json.loads(payload))


def test_steady_shrink_needs_streak_time_and_a_steady_count():
    day_ago = (NOW - timedelta(hours=25)).isoformat()
    assert _steady_shrink(3, [738, 738, 740], day_ago, now=NOW)
    assert not _steady_shrink(2, [738, 738], day_ago, now=NOW)  # too few checks
    assert not _steady_shrink(3, [738, 738, 738], (NOW - timedelta(hours=2)).isoformat(), now=NOW)  # too soon
    assert not _steady_shrink(3, [738, 300, 738], day_ago, now=NOW)  # a flapping, truncating monitor


async def test_guard_state_comes_from_the_db_not_the_cached_config():
    conn = FakeConn(2237, 1499, streak=4, suspect_counts=[738, 738], suspect_since=NOW.isoformat())
    gone, reason = await _mark_gone_with_guards(conn, "b", 738, NOW, {"suspect_streak": 1}, 2, LOG)
    assert (gone, reason) == (0, "blast_radius")
    assert conn.writes[-1]["suspect_streak"] == 5
    assert conn.writes[-1]["suspect_counts"] == [738, 738, 738]


async def test_a_day_of_steady_blast_radius_skips_delists_and_keeps_the_streak():
    since = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    conn = FakeConn(2237, 1499, streak=5, suspect_counts=[738, 738], suspect_since=since)
    gone, reason = await _mark_gone_with_guards(conn, "b", 738, NOW, {}, 2, LOG)
    assert (gone, reason) == (1499, None)
    assert conn.writes[-1]["suspect_streak"] == 6  # the rows need more checks to reach the threshold
    assert conn.writes[-1]["recent_discovered_counts"] == [738]


async def test_a_passing_check_clears_the_suspect_state():
    conn = FakeConn(800, 10, history=[790, 800, 805], streak=2, suspect_counts=[400, 790],
                    suspect_since=NOW.isoformat())
    gone, reason = await _mark_gone_with_guards(conn, "b", 795, NOW, {}, 2, LOG)
    assert (gone, reason) == (10, None)
    assert conn.writes[-1]["suspect_streak"] == 0 and conn.writes[-1]["suspect_since"] is None
    assert conn.writes[-1]["recent_discovered_counts"] == [790, 800, 805, 795]
