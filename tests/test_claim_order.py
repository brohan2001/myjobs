"""claim_work.lua must serve board checks (monitors) before job-page scrapes.

On 2026-10-14, 2,371 of 2,845 boards were >2 h overdue: domains with first-time scrapes sat in
tier 0, which was tried first on every claim, so the 1,370 due Greenhouse monitors in tier 1
were never claimed.
"""

from pathlib import Path

import fakeredis
import pytest

LUA = (Path(__file__).parent.parent / "src" / "lua" / "claim_work.lua").read_text()
NOW = 1_800_000_000.0


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def claim(r):
    return r.eval(LUA, 0, "simple", NOW, 2.0, 10, 600)


def test_due_monitor_domain_beats_scrape_backlog_domains(r):
    # 15 domains with first-time scrapes (tier 0), one ATS domain with a due monitor (tier 1).
    for i in range(15):
        d = f"jobs{i}.example.com"
        r.zadd(f"ft_scrapes_simple:{d}", {f"posting-{i}": 0})
        r.zadd("ready:simple:0", {d: 0})
    r.zadd("monitors_simple:greenhouse", {"board-1": NOW - 172_800})
    r.zadd("ready:simple:1", {"greenhouse": NOW - 172_800})

    assert claim(r) == ["board-1", "monitor", "greenhouse"]


def test_within_a_domain_due_monitor_beats_first_time_scrapes(r):
    d = "acme.wd5.myworkdayjobs.com"
    r.zadd(f"ft_scrapes_simple:{d}", {"posting-1": 0, "posting-2": 0})
    r.zadd(f"monitors_simple:{d}", {"board-acme": NOW - 60})
    r.zadd("ready:simple:0", {d: 0})

    assert claim(r) == ["board-acme", "monitor", d]
    assert claim(r) is None  # domain is now rate-limited
    assert r.zcard(f"ft_scrapes_simple:{d}") == 2


def test_first_time_monitor_still_comes_first(r):
    d = "jobs.lever.co"
    r.zadd(f"ft_monitors_simple:{d}", {"new-board": 0})
    r.zadd(f"monitors_simple:{d}", {"old-board": NOW - 60})
    r.zadd("ready:simple:0", {d: 0})

    assert claim(r) == ["new-board", "monitor", d]


def test_scrapes_are_served_when_no_monitor_is_due(r):
    r.zadd("ft_scrapes_simple:a.example.com", {"posting-1": 0})
    r.zadd("ready:simple:0", {"a.example.com": 0})
    r.zadd("monitors_simple:greenhouse", {"board-1": NOW + 3600})
    r.zadd("ready:simple:1", {"greenhouse": NOW + 3600})

    assert claim(r) == ["posting-1", "scrape", "a.example.com"]
