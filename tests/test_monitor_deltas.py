"""myjobs deltas to vendored monitors: join.com page layouts, nextdata exact_total."""

import json

import httpx
import pytest

from src.core.monitors.join import discover
from src.core.monitors.nextdata import _validate_total_records


def _page(root: str, ids: list[int]) -> str:
    items = [{"idParam": f"{i}-engineer", "id": i, "title": "Engineer"} for i in ids]
    data = {"props": {"pageProps": {root: {"jobs": {
        "items": items, "pagination": {"page": 1, "pageCount": 1, "total": len(items)}}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


async def _discover(root: str) -> set[str]:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=_page(root, [1, 2])))
    async with httpx.AsyncClient(transport=transport) as client:
        return set(await discover({"board_url": "https://join.com/companies/acme", "metadata": {}}, client))


async def test_join_reads_new_page_data_layout():
    assert await _discover("pageData") == {"https://join.com/companies/acme/1-engineer",
                                           "https://join.com/companies/acme/2-engineer"}


async def test_join_reads_old_initial_state_layout():
    assert len(await _discover("initialState")) == 2


def test_exact_total_false_accepts_repeated_rows():
    data = {"s": {"totalRecords": 120}}
    cfg = {"path": "s", "total_records": "totalRecords", "exact_total": False}
    _validate_total_records({f"u{i}" for i in range(100)}, data, cfg, board_url="b")  # repeats: fine
    with pytest.raises(RuntimeError):
        _validate_total_records({f"u{i}" for i in range(50)}, data, cfg, board_url="b")
    with pytest.raises(RuntimeError):  # default stays exact
        _validate_total_records({f"u{i}" for i in range(100)}, data, {**cfg, "exact_total": True}, board_url="b")
