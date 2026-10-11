"""Characterization of ``fetch_with_retry`` (src/shared/http_retry.py)."""

from __future__ import annotations

import httpx
import pytest

from src.shared.http_retry import (
    END_OF_PAGINATION_STATUSES,
    PaginationFetchError,
    fetch_with_retry,
    is_retryable_status,
)

URL = "https://example.com/page"


async def test_503_then_200_succeeds(make_client, sleeps):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, text="hello")

    async with make_client(handler) as client:
        assert await fetch_with_retry(client, URL) == "hello"
    assert len(calls) == 2
    assert len(sleeps) == 1
    assert 0.25 <= sleeps[0] <= 0.75  # base 0.5 * 2^0 * (0.5..1.5)


async def test_persistent_503_raises_pagination_fetch_error(make_client, sleeps):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await fetch_with_retry(client, URL)
    err = ei.value
    assert (err.url, err.attempts, err.last_status, err.last_error) == (URL, 3, 503, None)
    assert len(calls) == 3
    assert len(sleeps) == 2  # no sleep after the final attempt


async def test_custom_retry_budget(make_client, sleeps):
    async with make_client(lambda r: httpx.Response(500)) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await fetch_with_retry(client, URL, retries=5)
    assert ei.value.attempts == 5 and len(sleeps) == 4


@pytest.mark.parametrize("status", sorted(END_OF_PAGINATION_STATUSES))
async def test_404_410_mean_end_of_pagination(make_client, sleeps, status):
    async with make_client(lambda r: httpx.Response(status)) as client:
        assert await fetch_with_retry(client, URL) is None
    assert sleeps == []


async def test_other_4xx_returns_none_without_retry(make_client, sleeps):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(403)

    async with make_client(handler) as client:
        assert await fetch_with_retry(client, URL) is None
    assert len(calls) == 1


async def test_transient_403_opt_in_retries_then_raises(make_client, sleeps):
    async with make_client(lambda r: httpx.Response(403)) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await fetch_with_retry(client, URL, transient_403=True)
    assert ei.value.last_status == 403 and ei.value.attempts == 3


async def test_429_is_retried(make_client, sleeps):
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(429) if n["c"] < 3 else httpx.Response(200, text="ok")

    async with make_client(handler) as client:
        assert await fetch_with_retry(client, URL) == "ok"


async def test_empty_200_is_transient(make_client, sleeps):
    async with make_client(lambda r: httpx.Response(200, text="")) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await fetch_with_retry(client, URL)
    assert ei.value.last_status == 200 and ei.value.last_error is None


async def test_network_exception_retried_then_error_records_type(make_client, sleeps):
    def handler(req):
        raise httpx.ConnectError("boom", request=req)

    async with make_client(handler) as client:
        with pytest.raises(PaginationFetchError) as ei:
            await fetch_with_retry(client, URL)
    assert ei.value.last_status is None
    assert ei.value.last_error == "ConnectError"


async def test_body_truncated_to_max_chars(make_client):
    async with make_client(lambda r: httpx.Response(200, text="x" * 100)) as client:
        assert await fetch_with_retry(client, URL, max_chars=10) == "x" * 10


def test_is_retryable_status():
    assert all(is_retryable_status(s) for s in (500, 503, 520, 599, 408, 425, 429))
    assert not any(is_retryable_status(s) for s in (200, 301, 400, 401, 403, 404, 410))
