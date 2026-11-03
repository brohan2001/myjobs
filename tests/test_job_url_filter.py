"""Which discovered URLs count as job pages (src/processing/board.py)."""

import pytest

from src.processing.board import _classify_job_url

BOARD = "https://careers.persistent.com/"


@pytest.mark.parametrize("url,reason", [
    ("https://careers.persistent.com/#!/jobdetail/dev-lead-pune-2026103009263921", None),  # SPA hash route
    ("https://careers.persistent.com/", "bare_host"),
    ("https://careers.persistent.com/#", "bare_host"),
    ("https://careers.persistent.com/#0", "bare_host"),
    ("https://careers.persistent.com/#!/", "bare_host"),
    ("https://acme.com/jobs/123", None),
])
def test_classify_job_url(url, reason):
    assert _classify_job_url(url, BOARD) == reason
