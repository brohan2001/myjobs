"""A check that turns up a pile of new undated jobs found old ones: they're marked backlog (D38)."""

from src.processing.board import _bulk_sighting


def test_first_page_of_old_jobs_is_bulk():
    assert _bulk_sighting(new=350, processed=400)  # NHS: 350 new on a board that had 50


def test_steady_trickle_is_not_bulk():
    assert not _bulk_sighting(new=12, processed=900)
    assert not _bulk_sighting(new=60, processed=2000)  # 3% of a big board in one check
    assert not _bulk_sighting(new=49, processed=49)  # a small board's first crawl is D38's job
