from __future__ import annotations

from uuid import UUID

import pytest

from src.api import admin
from src.config import settings

TOKEN = "s3cret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BOARD_ID = UUID(int=7)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOKEN)


def test_admin_hidden_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    assert client.get("/api/admin/boards", headers=AUTH).status_code == 404


def test_admin_rejects_wrong_token(client, token):
    assert client.get("/api/admin/boards").status_code == 401
    assert client.get("/api/admin/boards", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_boards_filters_and_page(client, pool, token):
    r = client.get("/api/admin/boards?q=acme&ats=greenhouse&status=failing&sort=recent&page=2", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"boards": [], "has_more": False}
    _, sql, args = pool.calls[0]
    assert "b.consecutive_failures > 0" in sql and "b.last_checked_at DESC" in sql
    assert args == ("acme", "greenhouse", admin.PAGE_SIZE + 1, admin.PAGE_SIZE)


def test_boards_rejects_unknown_status(client, token):
    assert client.get("/api/admin/boards?status=drop table", headers=AUTH).status_code == 400


def _board_row():
    return {"id": BOARD_ID, "board_url": "https://boards.greenhouse.io/acme", "crawler_type": "greenhouse",
            "company_id": UUID(int=1), "metadata": "{}", "check_interval_minutes": 60, "scrape_interval_hours": 24,
            "throttle_key": "greenhouse.io", "monitor_needs_browser": False, "scraper_needs_browser": False}


def test_recrawl_enqueues_at_front(client, pool, token, monkeypatch):
    calls = []

    async def fake_enqueue(domain, board_id, next_check_at, config, *, browser, first_time):
        calls.append((domain, board_id, browser, first_time, config["crawler_type"]))

    monkeypatch.setattr("src.redis_queue.enqueue_monitor", fake_enqueue)
    pool.fetchrow_row = _board_row()
    assert client.post(f"/api/admin/boards/{BOARD_ID}/recrawl", headers=AUTH).json() == {"ok": True}
    assert calls == [("greenhouse.io", str(BOARD_ID), False, True, "greenhouse")]


def test_recrawl_unknown_board_404(client, pool, token):
    pool.fetchrow_row = None
    assert client.post(f"/api/admin/boards/{BOARD_ID}/recrawl", headers=AUTH).status_code == 404


def test_disable_removes_from_queue_and_feed(client, pool, token, monkeypatch):
    removed = []

    async def fake_remove(domain, board_id):
        removed.append((domain, board_id))

    monkeypatch.setattr("src.redis_queue.remove_monitor", fake_remove)
    pool.fetchrow_row = {"id": BOARD_ID, "throttle_key": "greenhouse.io"}
    assert client.post(f"/api/admin/boards/{BOARD_ID}/disable", headers=AUTH).status_code == 200
    assert removed == [("greenhouse.io", str(BOARD_ID))]
    assert pool.calls[-1][0] == "execute" and "job_posting" in pool.calls[-1][1]
