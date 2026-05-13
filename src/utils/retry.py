from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, TypeVar

import httpx

T = TypeVar("T")

_log = None  # lazy to avoid circular import at module load time


def _get_log():
    global _log
    if _log is None:
        from src.logger import get_logger
        _log = get_logger("retry")
    return _log


def _compute_delay(
    response: httpx.Response | None,
    attempt: int,
    base_delay: float,
    max_delay: float,
) -> float:
    """Exponential backoff with jitter, honoring Retry-After header if present."""
    if response is not None:
        raw = response.headers.get("Retry-After", "")
        if raw:
            try:
                return min(float(raw), max_delay)
            except ValueError:
                pass
            try:
                dt = parsedate_to_datetime(raw)
                wait = (dt - datetime.now(timezone.utc)).total_seconds()
                return min(max(wait, 0.0), max_delay)
            except Exception:
                pass
    delay = base_delay * (2 ** attempt) + random.uniform(0, 1.0)
    return min(delay, max_delay)


async def async_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> T:
    """Retry an async callable with exponential backoff + jitter.

    Retries on httpx.HTTPStatusError with a retryable status, or on any
    httpx.RequestError (network/timeout). All other exceptions propagate immediately.
    """
    log = _get_log()
    last_exc: BaseException | None = None

    for attempt in range(max_retries):
        try:
            return await fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in retryable_statuses:
                raise
            last_exc = exc
            delay = _compute_delay(exc.response, attempt, base_delay, max_delay)
            log.warning(
                "http_retry",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "status": exc.response.status_code,
                    "delay_s": round(delay, 2),
                    "url": str(exc.request.url),
                },
            )
            await asyncio.sleep(delay)
        except httpx.RequestError as exc:
            last_exc = exc
            delay = _compute_delay(None, attempt, base_delay, max_delay)
            log.warning(
                "network_retry",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "error": type(exc).__name__,
                    "delay_s": round(delay, 2),
                },
            )
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc
