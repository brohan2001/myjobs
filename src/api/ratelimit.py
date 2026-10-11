"""Per-client fixed-window rate limiting for the public API.

Uses Redis when it's reachable (shared across API processes), and an
in-process window otherwise, so a Redis outage doesn't take the read API down.
"""
from __future__ import annotations

import time
from collections import OrderedDict

from src.logger import get_logger

log = get_logger(__name__)


class RateLimiter:
    def __init__(self, limit: int, window_s: int = 60, redis=None, max_local_keys: int = 50_000) -> None:
        self.limit = limit
        self.window_s = window_s
        self.redis = redis
        self._local: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self._max_local_keys = max_local_keys

    def _window(self, now: float) -> int:
        return int(now // self.window_s)

    async def hit(self, key: str, *, now: float | None = None) -> tuple[bool, int, int]:
        """Count one request. Returns (allowed, remaining, seconds_until_reset)."""
        now = time.time() if now is None else now
        window = self._window(now)
        reset_in = self.window_s - int(now % self.window_s)
        count: int | None = None
        if self.redis is not None:
            try:
                rkey = f"api:rl:{key}:{window}"
                pipe = self.redis.pipeline()
                pipe.incr(rkey)
                pipe.expire(rkey, self.window_s + 1)
                count = int((await pipe.execute())[0])
            except Exception:  # noqa: BLE001 - fall back to local counting
                log.warning("api.ratelimit.redis_unavailable")
                count = None
        if count is None:
            count = self._local_hit(key, window)
        return count <= self.limit, max(0, self.limit - count), reset_in

    def _local_hit(self, key: str, window: int) -> int:
        prev = self._local.pop(key, None)
        count = prev[1] + 1 if prev and prev[0] == window else 1
        self._local[key] = (window, count)
        while len(self._local) > self._max_local_keys:
            self._local.popitem(last=False)
        return count
