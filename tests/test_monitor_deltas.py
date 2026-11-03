"""myjobs deltas to vendored monitors: join.com page layouts, nextdata exact_total, Oracle HCM custom domains."""

import json

import httpx
import pytest

from src.core.monitors.join import discover
from src.core.monitors.nextdata import _validate_total_records
from src.core.monitors.oracle_hcm import _normalize_oracle_host, _parse_candidate_url


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


def test_oracle_hcm_accepts_listed_custom_domains_only():
    url = "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/CX_1001"
    assert _parse_candidate_url(url) == ("enterpriseplatform.dell.com", "CX_1001", None)
    assert _normalize_oracle_host("hdpc.fa.us2.oraclecloud.com")
    assert _normalize_oracle_host("evil.example.com") is None


def test_set_body_param_reaches_into_a_json_form_field():
    from urllib.parse import parse_qs

    from src.shared.api_sniff import set_body_param

    body = set_body_param('domain=x&filterCri={"paginationStartNo":0,"n":10}', "filterCri.paginationStartNo", 20)
    assert json.loads(parse_qs(body)["filterCri"][0]) == {"paginationStartNo": 20, "n": 10}
    assert parse_qs(body)["domain"] == ["x"]
