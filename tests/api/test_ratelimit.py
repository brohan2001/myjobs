from __future__ import annotations

from src.api.ratelimit import RateLimiter


async def test_local_allows_up_to_limit_then_blocks():
    rl = RateLimiter(3, window_s=60)
    results = [await rl.hit("a", now=1000.0) for _ in range(5)]
    assert [r[0] for r in results] == [True, True, True, False, False]
    assert [r[1] for r in results] == [2, 1, 0, 0, 0]


async def test_reset_in_value():
    rl = RateLimiter(1, window_s=60)
    _, _, reset = await rl.hit("a", now=120.0)
    assert reset == 60
    _, _, reset = await rl.hit("a", now=150.0)
    assert reset == 30
    _, _, reset = await rl.hit("a", now=179.0)
    assert reset == 1


async def test_window_rollover_resets_count():
    rl = RateLimiter(1, window_s=60)
    assert (await rl.hit("a", now=60.0))[0] is True
    assert (await rl.hit("a", now=100.0))[0] is False
    assert (await rl.hit("a", now=120.0))[0] is True


async def test_keys_are_independent():
    rl = RateLimiter(1)
    assert (await rl.hit("a", now=0.0))[0]
    assert (await rl.hit("b", now=0.0))[0]
    assert not (await rl.hit("a", now=0.0))[0]


async def test_lru_eviction_bound():
    rl = RateLimiter(5, max_local_keys=3)
    for k in "abcd":
        await rl.hit(k, now=0.0)
    assert len(rl._local) == 3
    assert "a" not in rl._local
    # touching b makes it most recent, so c is evicted next
    await rl.hit("b", now=0.0)
    await rl.hit("e", now=0.0)
    assert set(rl._local) == {"d", "b", "e"}


class FakePipe:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def incr(self, k):
        self.ops.append(("incr", k))

    def expire(self, k, s):
        self.ops.append(("expire", k, s))

    async def execute(self):
        if self.redis.fail:
            raise ConnectionError("redis down")
        k = self.ops[0][1]
        self.redis.counts[k] = self.redis.counts.get(k, 0) + 1
        return [self.redis.counts[k], True]


class FakeRedis:
    def __init__(self, fail=False):
        self.fail = fail
        self.counts = {}
        self.pipes = []

    def pipeline(self):
        p = FakePipe(self)
        self.pipes.append(p)
        return p


async def test_redis_mode_counts_in_redis():
    r = FakeRedis()
    rl = RateLimiter(2, window_s=60, redis=r)
    out = [await rl.hit("ip", now=120.0) for _ in range(3)]
    assert [o[0] for o in out] == [True, True, False]
    assert list(r.counts) == ["api:rl:ip:2"]
    assert r.pipes[0].ops == [("incr", "api:rl:ip:2"), ("expire", "api:rl:ip:2", 61)]
    assert not rl._local


async def test_redis_failure_falls_back_to_local():
    rl = RateLimiter(2, redis=FakeRedis(fail=True))
    out = [await rl.hit("ip", now=0.0) for _ in range(3)]
    assert [o[0] for o in out] == [True, True, False]
    assert rl._local["ip"][1] == 3


async def test_redis_pipeline_creation_raising_falls_back():
    class Boom:
        def pipeline(self):
            raise RuntimeError("nope")

    rl = RateLimiter(1, redis=Boom())
    assert (await rl.hit("ip", now=0.0))[0] is True
    assert (await rl.hit("ip", now=0.0))[0] is False
