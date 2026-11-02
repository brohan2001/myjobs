"""Publish dates in the formats ATS feeds send (Phase 3: posted-date accuracy)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.processing.cpu import _coerce_datetime, _vague_old_date

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("2026-10-28T09:30:00Z", datetime(2026, 10, 28, 9, 30, tzinfo=UTC)),
        ("2026-10-28", datetime(2026, 10, 28, tzinfo=UTC)),
        ("Wed, 28 Oct 2026 10:00:00 GMT", datetime(2026, 10, 28, 10, tzinfo=UTC)),
        ("1793000000000", datetime.fromtimestamp(1793000000, tz=UTC)),  # ByteDance create_time, epoch ms
        (1793000000000, datetime.fromtimestamp(1793000000, tz=UTC)),
        (1793000000, datetime.fromtimestamp(1793000000, tz=UTC)),
        ("10/25/2026", datetime(2026, 10, 25, tzinfo=UTC)),  # Workday postedOn
        ("25.10.2026", datetime(2026, 10, 25, tzinfo=UTC)),
        ("28 Oct 2026", datetime(2026, 10, 28, tzinfo=UTC)),
        ("Oct 28, 2026", datetime(2026, 10, 28, tzinfo=UTC)),
        ("October 28, 2026", datetime(2026, 10, 28, tzinfo=UTC)),
        ("Posted Today", NOW),
        ("Posted Yesterday", NOW - timedelta(days=1)),
        ("Posted 3 Days Ago", NOW - timedelta(days=3)),
        ("5 hours ago", NOW - timedelta(hours=5)),
    ],
)
def test_reads_feed_formats(raw, want):
    assert _coerce_datetime(raw, now=NOW) == want


@pytest.mark.parametrize(
    "raw",
    [None, "", "Posted 30+ Days Ago", "soon", "1999-12-31", "2026-11-10", True, "Recently"],
)
def test_unknown_or_implausible_is_none(raw):
    assert _coerce_datetime(raw, now=NOW) is None


def test_vague_old_dates():
    assert _vague_old_date("Posted more than 1 month ago")  # Accenture
    assert _vague_old_date("Posted 30+ Days Ago")  # Workday
    assert not _vague_old_date("Posted 3 days ago")
    assert not _vague_old_date(None)
