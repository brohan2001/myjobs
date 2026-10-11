"""Location arrays keep work mode for location-less remote postings."""
from __future__ import annotations

from src.core.location_resolve import ResolvedLocation
from src.processing.cpu import _resolve_locations_sync


class _FakeResolver:
    def __init__(self, results):
        self._results = results

    def resolve(self, locations, job_location_type, posting_language=None):
        return self._results


def test_remote_without_location_kept_as_null_id():
    r = _FakeResolver([ResolvedLocation(location_id=None, location_type="remote")])
    assert _resolve_locations_sync(r, ["Remote"], None) == ([None], ["remote"])


def test_onsite_without_location_dropped():
    r = _FakeResolver([ResolvedLocation(location_id=None, location_type="onsite")])
    assert _resolve_locations_sync(r, ["Somewhere"], None) == (None, None)


def test_mixed_resolved_and_remote():
    r = _FakeResolver([
        ResolvedLocation(location_id=1277333, location_type="onsite"),
        ResolvedLocation(location_id=None, location_type="remote"),
    ])
    assert _resolve_locations_sync(r, ["Bengaluru", "Remote"], None) == ([1277333, None], ["onsite", "remote"])
