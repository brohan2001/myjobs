"""A domain with queued tasks must never lose its ready entry.

On 2026-11-02, 543 domains (651 boards and postings) had tasks queued but no ready entry, so no worker claimed them
for 17 h. claim_work dropped a due domain whose remaining tasks were not due yet (after remove_monitor or the scrape
prune took its earliest task), and sync no longer re-added scheduled boards, so nothing repaired it.
"""

from pathlib import Path

import fakeredis
import pytest

LUA_DIR = Path(__file__).parent.parent / "src" / "lua"
CLAIM = (LUA_DIR / "claim_work.lua").read_text()
ENQUEUE = (LUA_DIR / "enqueue_task.lua").read_text()
NOW = 1_800_000_000.0


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def ready_tiers(r, domain):
    return {t: r.zscore(f"ready:simple:{t}", domain) for t in range(3) if r.zscore(f"ready:simple:{t}", domain)}


def test_due_domain_with_only_later_tasks_is_refiled_not_dropped(r):
    # The due board was removed (remove_monitor), leaving the ready entry due and one board due in an hour.
    r.zadd("monitors_simple:acme.example.com", {"board-2": NOW + 3600})
    r.zadd("ready:simple:1", {"acme.example.com": NOW - 60})

    assert r.eval(CLAIM, 0, "simple", NOW, 2.0, 10, 600) is None
    assert ready_tiers(r, "acme.example.com") == {1: NOW + 3600}


def test_due_domain_with_no_tasks_is_dropped(r):
    r.zadd("ready:simple:1", {"empty.example.com": NOW - 60})

    assert r.eval(CLAIM, 0, "simple", NOW, 2.0, 10, 600) is None
    assert ready_tiers(r, "empty.example.com") == {}


def test_enqueue_refiles_a_queued_task_whose_domain_has_no_ready_entry(r):
    r.zadd("monitors_simple:acme.example.com", {"board-1": NOW + 600})

    added = r.eval(ENQUEUE, 0, "simple", "acme.example.com", "board-1", NOW, "monitor", "0", NOW)

    assert added == 0  # the board keeps its due time
    assert r.zscore("monitors_simple:acme.example.com", "board-1") == NOW + 600
    assert ready_tiers(r, "acme.example.com") == {1: NOW + 600}


def test_enqueue_leaves_a_filed_domain_alone(r):
    r.zadd("monitors_simple:acme.example.com", {"board-1": NOW + 600})
    r.zadd("ready:simple:1", {"acme.example.com": NOW + 900})  # e.g. pushed back by its rate limit

    r.eval(ENQUEUE, 0, "simple", "acme.example.com", "board-1", NOW, "monitor", "0", NOW)

    assert ready_tiers(r, "acme.example.com") == {1: NOW + 900}
