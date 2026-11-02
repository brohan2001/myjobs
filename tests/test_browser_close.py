"""A wedged Playwright close() must not hang cleanup or task cancellation (regression from 2026-10-11)."""

import asyncio

from src.shared import browser


class Wedged:
    async def close(self):
        await asyncio.Event().wait()


class Broken:
    async def close(self):
        raise RuntimeError("browser gone")


async def test_close_is_bounded(monkeypatch):
    monkeypatch.setattr(browser, "BROWSER_CLOSE_TIMEOUT_SECONDS", 0.05)
    await asyncio.wait_for(browser._close_browser_resource(Wedged(), "browser"), timeout=1)


async def test_close_swallows_errors():
    await browser._close_browser_resource(Broken(), "browser")


async def test_cancel_unwinds_through_a_wedged_close(monkeypatch):
    monkeypatch.setattr(browser, "BROWSER_CLOSE_TIMEOUT_SECONDS", 0.05)

    async def work():
        try:
            await asyncio.Event().wait()
        finally:
            await browser._close_browser_resource(Wedged(), "browser")

    task = asyncio.create_task(work())
    await asyncio.sleep(0)
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=1)
    assert done and task.cancelled()
