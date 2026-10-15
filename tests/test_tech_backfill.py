"""Backfill verdicts: deactivate what a board check would now drop, flag the rest by title."""

import pytest

from src.processing.tech_backfill import classify


def row(title, url="https://x.io/jobs/1", crawler_type="greenhouse", is_tech=True, metadata="{}"):
    return {"title": title, "source_url": url, "crawler_type": crawler_type, "is_tech": is_tech, "metadata": metadata}


@pytest.mark.parametrize("r,verdict", [
    (row("Cashier"), "drop"),  # rich board: the monitor drops it from now on
    (row("Data Engineer"), None),
    (row(None, "https://mcd.com/job/Restaurant-Crew-Member/1", "sitemap"), "drop"),  # slug says non-tech
    (row("Cashier", "https://x.io/jobs/1", "sitemap"), "non_tech"),  # URL-only: keep active, hide
    (row("Data Engineer", "https://x.io/jobs/1", "sitemap", is_tech=False), "tech"),  # classifier changed
    (row("Data Engineer", "https://x.io/jobs/1", "sitemap"), None),
    (row(None, "https://x.io/jobs/1", "sitemap"), None),  # not scraped yet
])
def test_classify(r, verdict):
    assert classify(r) == verdict
