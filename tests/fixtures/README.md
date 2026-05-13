# Test Fixtures

Static API response payloads used by `tests/test_parsers.py` to regression-test scraper parsing logic.

## Fixture files

| File | Source | ATS | Notes |
|------|--------|-----|-------|
| `greenhouse_anthropic.json` | Live capture | Greenhouse | `GET /v1/boards/anthropic/jobs?content=true` |
| `lever_wealthfront.json` | Live capture | Lever | `GET /v0/postings/wealthfront?mode=json&limit=50` |
| `amazon_amazon.json` | Live capture | Amazon | `GET /en/search.json?...` |
| `workday_synthetic.json` | Synthetic | Workday | Hand-crafted to match Workday API schema (live API returning 422 at time of capture) |
| `google_synthetic.json` | Synthetic | Google | Hand-crafted to match Careers API v3 schema (endpoint returning 404 at time of capture) |
| `apple_synthetic.json` | Synthetic | Apple | Hand-crafted to match Apple Jobs API schema (endpoint redirecting to 404 at time of capture) |

## Re-capturing live fixtures

Run from the project root (requires internet access, ~30 seconds):

```bash
# Delete existing fixture(s) first to force re-capture
rm tests/fixtures/greenhouse_anthropic.json
python3 scripts/capture_fixtures.py
```

The capture script patches `BaseScraper._request` to intercept and save the first JSON response per ATS type. It only writes a file if it doesn't already exist, so partial runs are safe to re-run.

## Synthetic fixtures

Synthetic fixtures are hand-crafted from the scraper source code to exercise the parsing path.
They should be updated whenever the target ATS API response schema changes.
