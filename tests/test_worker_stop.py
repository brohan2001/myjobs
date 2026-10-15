"""The worker's stop handler: drain on the first signal, force-exit on the second or after a timeout."""

import asyncio

import pytest

from src import cli


class FakeLoop:
    def __init__(self):
        self.later = []

    def call_later(self, delay, fn, *args):
        self.later.append((delay, fn, args))


def test_first_signal_drains_and_arms_a_hard_exit(monkeypatch):
    exits = []
    monkeypatch.setattr(cli.os, "_exit", exits.append)
    loop, event = FakeLoop(), asyncio.Event()

    cli._request_stop(loop, event)

    assert event.is_set()
    assert exits == []
    assert loop.later == [(cli._HARD_EXIT_AFTER_S, cli.os._exit, (1,))]


def test_second_signal_exits_immediately(monkeypatch):
    def fake_exit(code):
        raise SystemExit(code)

    monkeypatch.setattr(cli.os, "_exit", fake_exit)
    loop, event = FakeLoop(), asyncio.Event()
    cli._request_stop(loop, event)

    with pytest.raises(SystemExit) as e:
        cli._request_stop(loop, event)
    assert e.value.code == 130
