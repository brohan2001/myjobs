"""A board check must skip re-extracting jobs whose stored content is unchanged (most re-listed jobs)."""

import pytest

from src.core.hashing import content_hash
from src.core.monitors import DiscoveredJob
from src.processing.cpu import _rich_row_unchanged

DESC = "<p>Build data pipelines in Bengaluru.</p>"


def job(**kw):
    base = dict(url="https://x.io/1", title="Data Engineer", description=DESC, locations=["Bengaluru"],
                employment_type="Full-time")
    return DiscoveredJob(**{**base, **kw})


def stored(**kw):
    base = dict(desc_hash=content_hash(DESC), titles=["Data Engineer"], locations_raw=["Bengaluru"],
                employment_type="full_time")
    return {**base, **kw}


def test_identical_row_is_skipped():
    assert _rich_row_unchanged(job(), stored())


def test_missing_locations_keep_the_stored_ones():
    assert _rich_row_unchanged(job(locations=None), stored())


@pytest.mark.parametrize("j,s", [
    (job(description="<p>New text</p>"), stored()),
    (job(title="Senior Data Engineer"), stored()),
    (job(locations=["Pune"]), stored()),
    (job(employment_type="Contract"), stored()),
    (job(), stored(desc_hash=None)),  # no stored description: must write it
    (job(), None),  # relisted rows aren't in the stored map
])
def test_changed_rows_are_updated(j, s):
    assert not _rich_row_unchanged(j, s)
