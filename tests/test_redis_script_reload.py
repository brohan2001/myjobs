"""A restarted Redis forgets its Lua scripts; the queue must reload them instead of failing every claim.

On 2026-10-31 the kernel OOM-killed Redis and it came back with an empty script cache. Every claim_work then
raised NoScriptError, and the feed froze for 36 h while all services stayed "active".
"""

import fakeredis
import pytest

from src import redis_queue


@pytest.fixture
def r(monkeypatch):
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(redis_queue, "get_redis", lambda: fake)
    monkeypatch.setattr(redis_queue, "_SHAS", {})
    return fake


async def test_claim_survives_a_flushed_script_cache(r):
    await redis_queue.enqueue_monitor("greenhouse", "board-1", 0.0, {"ats": "greenhouse"}, first_time=True)
    await r.script_flush()  # what a Redis restart does to the script cache
    work = await redis_queue.claim_work()
    assert work is not None and work.task_id == "board-1"
