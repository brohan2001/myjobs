from __future__ import annotations

from src.scrapers.base import BaseScraper


class _Scraper(BaseScraper):
    """Minimal concrete subclass for testing BaseScraper logic."""
    async def fetch_jobs(self, company, company_id):
        return []


def _jobs(ids: list[str], ats: str = "greenhouse") -> list[dict]:
    return [{"external_id": i, "ats_type": ats} for i in ids]


class TestDeduplicate:
    def test_all_new_returns_all(self):
        s = _Scraper()
        result = s.deduplicate(_jobs(["1", "2", "3"]), existing_keys=set())
        assert len(result) == 3

    def test_all_existing_returns_empty(self):
        s = _Scraper()
        existing = {("1", "greenhouse"), ("2", "greenhouse")}
        result = s.deduplicate(_jobs(["1", "2"]), existing)
        assert result == []

    def test_mixed_returns_only_new(self):
        s = _Scraper()
        existing = {("1", "greenhouse")}
        result = s.deduplicate(_jobs(["1", "2", "3"]), existing)
        assert len(result) == 2
        assert all(j["external_id"] != "1" for j in result)

    def test_intra_batch_duplicates_deduplicated(self):
        s = _Scraper()
        # "1" appears twice in the same batch
        jobs = _jobs(["1", "1", "2"])
        result = s.deduplicate(jobs, existing_keys=set())
        assert len(result) == 2

    def test_same_external_id_different_ats_not_deduped(self):
        s = _Scraper()
        jobs = [
            {"external_id": "1", "ats_type": "greenhouse"},
            {"external_id": "1", "ats_type": "lever"},
        ]
        result = s.deduplicate(jobs, existing_keys=set())
        assert len(result) == 2

    def test_empty_jobs_returns_empty(self):
        s = _Scraper()
        result = s.deduplicate([], existing_keys=set())
        assert result == []
