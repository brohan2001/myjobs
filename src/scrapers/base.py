from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

import httpx


class ScraperError(Exception):
    pass


class BaseScraper(ABC):
    def __init__(self, rate_limit_rps: float = 0.5):
        self._min_interval = 1.0 / rate_limit_rps
        self._last_request: float = 0.0
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseScraper":
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)",
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=20.0,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self.client:
            await self.client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        elapsed = time.monotonic() - self._last_request
        wait = self._min_interval - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self.client.request(method, url, **kwargs)
                self._last_request = time.monotonic()
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** (attempt + 2))
                    continue
                if resp.status_code in (403, 404):
                    raise ScraperError(f"HTTP {resp.status_code}: {url}")
                resp.raise_for_status()
                return resp
            except ScraperError:
                raise
            except httpx.TimeoutException as e:
                last_exc = e
                await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as e:
                last_exc = e
                await asyncio.sleep(2 ** attempt)

        raise ScraperError(f"Failed after 3 attempts: {url}") from last_exc

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    def deduplicate(self, jobs: list[dict], existing_keys: set[tuple]) -> list[dict]:
        seen: set[tuple] = set()
        result = []
        for job in jobs:
            key = (job["external_id"], job["ats_type"])
            if key not in existing_keys and key not in seen:
                seen.add(key)
                result.append(job)
        return result

    @abstractmethod
    async def fetch_jobs(self, company: dict, company_id: int) -> list[dict]:
        ...
