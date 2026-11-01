"""The India-priority loop (D36) must survive a failed run and let a later run retry."""

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
    await asyncio.wait_for(priority.priority_loop(_Pool(), stop), timeout=2)
    assert len(calls) == 2
