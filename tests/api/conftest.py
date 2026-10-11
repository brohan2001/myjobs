"""Shared fixtures: synthetic location tree, fake asyncpg pool, app client."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.locations import LocationIndex
from src.api.ratelimit import RateLimiter

IN_ID, KA_ID, BLR_ID = 1, 2, 3
US_ID, CA_ID, SF_ID = 10, 11, 12
APAC_ID = -3

LOCATION_ROWS = [
    {"id": IN_ID, "parent_id": None, "type": "country", "code": "IN", "population": 1_400_000_000, "name": "India"},
    {"id": KA_ID, "parent_id": IN_ID, "type": "region", "code": "IN.19", "population": 60_000_000, "name": "Karnataka"},
    {"id": BLR_ID, "parent_id": KA_ID, "type": "city", "code": None, "population": 8_400_000, "name": "Bengaluru"},
    {"id": US_ID, "parent_id": None, "type": "country", "code": "US", "population": 330_000_000, "name": "United States"},
    {"id": CA_ID, "parent_id": US_ID, "type": "region", "code": "US.CA", "population": 39_000_000, "name": "California"},
    {"id": SF_ID, "parent_id": CA_ID, "type": "city", "code": None, "population": 870_000, "name": "San Francisco"},
    {"id": APAC_ID, "parent_id": None, "type": "macro", "code": "APAC", "population": 0, "name": "Asia Pacific"},
]
MACRO_ROWS = [{"macro_id": APAC_ID, "country_id": IN_ID}]


@pytest.fixture
def index() -> LocationIndex:
    return LocationIndex.from_rows(LOCATION_ROWS, MACRO_ROWS)


def make_job_row(n: int = 0, **over) -> dict:
    row = {
        "id": UUID(int=n + 1),
        "title": f"Engineer {n}",
        "url": f"https://example.com/{n}",
        "location_ids": [BLR_ID],
        "location_types": ["onsite"],
        "locations_raw": ["Bengaluru"],
        "employment_type": "full_time",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_period": None,
        "first_seen_at": datetime(2026, 1, 1, 12, 0, n % 60, tzinfo=timezone.utc),
        "last_seen_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "company_slug": "acme",
        "company_name": "Acme",
        "company_website": "https://acme.test",
        "company_logo": None,
        "company_type": "product",
        "ats": "greenhouse",
    }
    row.update(over)
    return row


class FakeConn:
    def __init__(self, pool):
        self.pool = pool

    async def fetch(self, sql, *args):
        self.pool.calls.append(("fetch", sql, args))
        return self.pool.fetch_rows

    async def fetchrow(self, sql, *args):
        self.pool.calls.append(("fetchrow", sql, args))
        return self.pool.fetchrow_row


class FakePool:
    def __init__(self):
        self.calls: list[tuple[str, str, tuple]] = []
        self.fetch_rows: list = []
        self.fetchrow_row = None

    def acquire(self):
        @asynccontextmanager
        async def _cm():
            yield FakeConn(self)
        return _cm()


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def make_client(pool, index):
    clients = []

    def _make(limit: int = 1000, app=None) -> TestClient:
        app = app or create_app(use_lifespan=False)
        app.state.pool = pool
        app.state.locations = index
        app.state.limiter = RateLimiter(limit)
        c = TestClient(app)
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.close()


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()
