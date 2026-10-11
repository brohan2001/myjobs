"""Snapshot of the registered monitors so accidental removal is caught.

CLAUDE.md claims 41 monitors; the code registers the names below (37).
Update the sets deliberately when adding/removing a monitor.
"""

from __future__ import annotations

import pytest

from src.core import monitors

EXPECTED_MONITORS = frozenset(
    {
        "accenture", "almacareer", "amazon", "api_sniffer", "ashby", "bite", "breezy", "deel",
        "dom", "dvinci", "eightfold", "gem", "greenhouse", "greythr", "hireology", "inline", "jobylon",
        "join", "keka", "lever", "mokahr", "nextdata", "notion", "oracle_hcm", "personio", "phenom",
        "pinpoint", "recruitee", "recruiter_co_kr", "rippling", "rss", "sitemap",
        "smartrecruiters", "softgarden", "traffit", "umantis", "workable", "workday",
        "ycombinator", "zoho_recruit",
    }
)

EXPECTED_RICH = frozenset(
    {
        "accenture", "almacareer", "amazon", "ashby", "deel", "dvinci", "gem", "greenhouse",
        "greythr", "hireology", "inline", "jobylon", "keka", "lever", "mokahr", "oracle_hcm", "pinpoint",
        "recruitee", "recruiter_co_kr", "rss", "traffit", "zoho_recruit",
    }
)


def test_registered_monitor_names_snapshot():
    assert monitors.all_monitor_types() == EXPECTED_MONITORS


def test_rich_monitor_snapshot():
    assert monitors.api_monitor_types() == EXPECTED_RICH


def test_registry_sorted_by_cost_and_names_unique():
    costs = [m.cost for m in monitors._REGISTRY]
    assert costs == sorted(costs)
    names = [m.name for m in monitors._REGISTRY]
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    "name,cost",
    [("greenhouse", 10), ("lever", 10), ("ashby", 10), ("workday", 10),
     ("smartrecruiters", 10), ("nextdata", 20), ("sitemap", 50), ("dom", 100)],
)
def test_key_monitor_costs(name, cost):
    by_name = {m.name: m for m in monitors._REGISTRY}
    assert by_name[name].cost == cost


def test_every_monitor_has_discover_and_stream():
    for m in monitors._REGISTRY:
        assert callable(m.discover)
        assert monitors.get_stream_fn(m.name) is not None


def test_unknown_monitor_raises():
    with pytest.raises(ValueError, match="Unknown monitor type"):
        monitors.get_discoverer("does-not-exist")


def test_browser_requirements():
    assert monitors.monitor_needs_browser("accenture")
    assert monitors.monitor_needs_browser("api_sniffer", {})
    assert not monitors.monitor_needs_browser("api_sniffer", {"api_url": "https://x"})
    assert monitors.monitor_needs_browser("dom", {"render": True})
    assert not monitors.monitor_needs_browser("greenhouse")


def test_is_rich_monitor_config_dependent():
    assert monitors.is_rich_monitor("greenhouse")
    assert not monitors.is_rich_monitor("api_sniffer")
    assert monitors.is_rich_monitor("api_sniffer", {"fields": {"title": "t"}})
    assert monitors.is_rich_monitor("nextdata", {"fields": {"title": "t"}})
    assert not monitors.is_rich_monitor("sitemap", {"fields": {"title": "t"}})


async def test_detect_monitor_type_picks_greenhouse_for_greenhouse_url(make_client, sleeps):
    """Cheaper probes (eightfold, join, phenom) run first and fall through on 404."""
    import httpx

    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        if req.url.host == "boards-api.greenhouse.io":
            return httpx.Response(200, json={"jobs": [{}, {}]})
        return httpx.Response(404)

    async with make_client(handler) as client:
        result = await monitors.detect_monitor_type("https://boards.greenhouse.io/acme", client)
    assert result == ("greenhouse", {"token": "acme", "jobs": 2})
    assert "boards-api.greenhouse.io" in hosts
