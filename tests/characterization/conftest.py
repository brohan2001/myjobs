"""Shared fixtures for characterization tests.

These tests pin the *current* behavior of the vendored scraping core. They
must never touch the network: an autouse fixture makes any real socket
connection (or DNS lookup) raise.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class NetworkAccessError(RuntimeError):
    """Raised when a characterization test tries to open a real connection."""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise NetworkAccessError("network access is forbidden in characterization tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


@pytest.fixture
def fixture_text() -> Callable[[str], str]:
    return lambda name: (FIXTURES / name).read_text()


@pytest.fixture
def fixture_json() -> Callable[[str], object]:
    return lambda name: json.loads((FIXTURES / name).read_text())


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Replace ``asyncio.sleep`` with an instant recorder; returns recorded delays."""
    recorded: list[float] = []
    real_sleep = asyncio.sleep

    async def _fake_sleep(delay, result=None):
        recorded.append(delay)
        await real_sleep(0)
        return result

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    return recorded


@pytest.fixture
def make_client() -> Callable[[Callable[[httpx.Request], httpx.Response]], httpx.AsyncClient]:
    """Build an ``httpx.AsyncClient`` backed by ``httpx.MockTransport(handler)``."""

    def _make(handler):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return _make
