"""The 6-hourly loop: India priority (D36) survives a failed run; lost scrapes are queued again (D41)."""

import asyncio

import fakeredis
import pytest

from src import priority


@pytest.fixture
def r(monkeypatch):
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(priority, "get_redis", lambda: fake)
    monkeypatch.setattr(priority, "RETRY_SECONDS", 0.01)
    return fake


class _Pool:
    def acquire(self):
        return self

    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


async def test_a_failed_run_frees_the_lock_and_retries(r, monkeypatch):
    calls = []
    stop = asyncio.Event()

    async def apply(conn):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("statement timeout")
        stop.set()

    monkeypatch.setattr(priority, "apply_india_priority", apply)
    monkeypatch.setattr(priority, "requeue_lost_scrapes", lambda conn: asyncio.sleep(0))
    await asyncio.wait_for(priority.priority_loop(_Pool(), stop), timeout=2)
    assert len(calls) == 2


async def test_requeue_lost_scrapes_queues_only_what_redis_lost(r, monkeypatch):
    queued = "11111111-1111-1111-1111-111111111111"
    lost = "22222222-2222-2222-2222-222222222222"
    await r.zadd("ft_scrapes_simple:acme.fa.oraclecloud.com", {queued: 0})
    rows = [
        {"id": pid, "url": f"https://acme.fa.oraclecloud.com/job/{n}", "r2_hash": None, "board_id": "b1",
         "metadata": '{"scraper_type": "oracle_hcm", "scraper_config": {"enrich": ["description"]}}',
         "crawler_type": "oracle_hcm"}
        for n, pid in enumerate((queued, lost))
    ]
    enqueued = []

    async def fake_enqueue(domain, pid, score, config, *, browser, first_time):
        enqueued.append((domain, pid, first_time))

    class _Conn:
        async def fetch(self, sql):
            return rows

    monkeypatch.setattr("src.processing.board._enqueue_scrape", fake_enqueue)
    assert await priority.requeue_lost_scrapes(_Conn()) == 1
    assert enqueued == [("acme.fa.oraclecloud.com", lost, True)]
