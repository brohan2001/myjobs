"""One-time script to capture real ATS API responses into tests/fixtures/.

Run once from the project root:
    python scripts/capture_fixtures.py

Existing fixture files are skipped (delete them first to re-capture).
Requires internet access. Rate-limited — takes ~30s total.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on the path when run directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scrapers.base import BaseScraper
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.amazon import AmazonScraper
from src.scrapers.google import GoogleScraper
from src.scrapers.apple import AppleScraper

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures"

# (ats_label, ScraperClass, company_dict, company_id, fixture_filename)
TARGETS = [
    (
        "greenhouse",
        GreenhouseScraper,
        {"name": "Anthropic", "slug": "anthropic", "ats_type": "greenhouse",
         "domain": "anthropic.com", "industry": "tech", "tier": 1},
        1,
        "greenhouse_anthropic.json",
    ),
    (
        "lever",
        LeverScraper,
        {"name": "Wealthfront", "slug": "wealthfront", "ats_type": "lever",
         "domain": "wealthfront.com", "industry": "fintech", "tier": 2},
        2,
        "lever_wealthfront.json",
    ),
    (
        "workday",
        WorkdayScraper,
        {
            "name": "Cisco",
            "slug": "cisco",
            "ats_type": "workday",
            "workday_host": "cisco.wd5.myworkdayjobs.com",
            "workday_slug": "Cisco",
            "workday_board": "Cisco",
            "domain": "cisco.com",
            "industry": "tech",
            "tier": 1,
        },
        3,
        "workday_cisco.json",
    ),
    (
        "amazon",
        AmazonScraper,
        {"name": "Amazon", "slug": "amazon", "ats_type": "amazon",
         "domain": "amazon.jobs", "industry": "tech", "tier": 1},
        4,
        "amazon_amazon.json",
    ),
    (
        "google",
        GoogleScraper,
        {"name": "Google", "slug": "google", "ats_type": "google",
         "domain": "google.com", "industry": "tech", "tier": 1},
        5,
        "google_google.json",
    ),
    (
        "apple",
        AppleScraper,
        {"name": "Apple", "slug": "apple", "ats_type": "apple",
         "domain": "apple.com", "industry": "tech", "tier": 1},
        6,
        "apple_apple.json",
    ),
]


async def capture_fixture(
    label: str,
    ScraperClass,
    company: dict,
    company_id: int,
    filename: str,
) -> bool:
    fixture_path = FIXTURE_DIR / filename
    if fixture_path.exists():
        print(f"  [skip] {filename} already exists")
        return True

    # Patch _request to intercept and save the first JSON response.
    captured: list[object] = []
    original_request = BaseScraper._request

    async def _capturing_request(self, method, url, **kwargs):
        resp = await original_request(self, method, url, **kwargs)
        if not captured:
            try:
                captured.append(resp.json())
                print(f"  Captured {method} {url[:80]}")
            except Exception as exc:
                print(f"  Warning: could not JSON-decode response: {exc}")
        return resp

    BaseScraper._request = _capturing_request  # type: ignore[method-assign]
    try:
        async with ScraperClass() as scraper:
            await scraper.fetch_jobs(company, company_id)
    except Exception as exc:
        print(f"  Warning: {label} scraper raised during capture: {exc}")
    finally:
        BaseScraper._request = original_request  # type: ignore[method-assign]

    if captured:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(json.dumps(captured[0], indent=2, default=str))
        size = fixture_path.stat().st_size
        print(f"  Saved {filename} ({size:,} bytes)")
        return True
    else:
        print(f"  ERROR: no response captured for {label}")
        return False


async def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for label, ScraperClass, company, company_id, filename in TARGETS:
        print(f"\n{label.upper()} ({company['slug']})...")
        success = await capture_fixture(label, ScraperClass, company, company_id, filename)
        if success:
            ok += 1
    print(f"\n{'='*50}")
    print(f"Captured {ok}/{len(TARGETS)} fixtures → {FIXTURE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
