import asyncio

from src.shared import browser


async def test_close_quietly_bounds_a_hung_close(monkeypatch):
    monkeypatch.setattr(browser, "CLOSE_TIMEOUT_S", 0.05)
    await asyncio.wait_for(browser._close_quietly(asyncio.Event().wait()), timeout=1)


async def test_close_quietly_swallows_errors():
    async def boom():
        raise RuntimeError("browser gone")

    await browser._close_quietly(boom())


async def test_cancel_unwinds_through_a_hung_close(monkeypatch):
    """Regression: a wedged browser.close() in a finally block made wait_for timeouts hang forever."""
    monkeypatch.setattr(browser, "CLOSE_TIMEOUT_S", 0.05)

    async def work():
        try:
            await asyncio.Event().wait()
        finally:
            await browser._close_quietly(asyncio.Event().wait())

    task = asyncio.create_task(work())
    await asyncio.sleep(0)
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=1)
    assert done and task.cancelled()
