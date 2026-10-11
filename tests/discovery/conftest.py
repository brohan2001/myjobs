"""Shared fixtures and network guard for discovery tests."""

from __future__ import annotations

import socket
from collections.abc import Callable

import httpx
import pytest


class NetworkAccessError(RuntimeError):
    """Raised when a test attempts network access."""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args, **kwargs):
        raise NetworkAccessError("network access is forbidden in discovery tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


@pytest.fixture
def make_mock_client() -> Callable[[Callable[[httpx.Request], httpx.Response] | None], httpx.AsyncClient]:
    """Factory fixture returning an httpx.AsyncClient with MockTransport."""

    def _make(handler: Callable[[httpx.Request], httpx.Response] | None = None) -> httpx.AsyncClient:
        if handler is None:
            handler = lambda req: httpx.Response(200, text="OK")
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return _make
