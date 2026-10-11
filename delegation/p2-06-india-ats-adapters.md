# p2-06-india-ats-adapters
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-06-india-ats-adapters` (already checked out)

## Goal
Add three crawler monitors for ATS platforms common among Indian employers: **Keka Hire**, **greytHR Hire** and **Zoho Recruit**. The endpoints were verified live (see `docs/research/INDIA_ATS.md` §2–3).

## Files you may touch (nothing else)
- `src/core/monitors/keka.py`, `src/core/monitors/greythr.py`, `src/core/monitors/zoho_recruit.py` (new)
- `src/core/monitors/__init__.py`: ONLY add the three names to the import list at the bottom (alphabetical).
- `tests/characterization/fixtures/keka_*.json`, `greythr_*.json`, `zoho_*.html` (new, trimmed to ≤ 5 jobs each)
- `tests/characterization/test_india_ats.py` (new)
- `tests/characterization/test_registry.py`: ONLY add the three names to `EXPECTED_MONITORS` and `EXPECTED_RICH`.

## Contract: copy the pattern of `src/core/monitors/pinpoint.py` exactly
Read `pinpoint.py` and `src/core/monitor.py` (`DiscoveredJob`) first. Each module:
- `async def discover(board: dict, client: httpx.AsyncClient, pw=None) -> list[DiscoveredJob]`. `board["board_url"]` is the tenant careers URL; `board.get("metadata")` may hold `{"tenant": "<sub>"}`. Use `fetch_with_retry` from `src/shared/http_retry.py` like other monitors do. Return rich `DiscoveredJob`s with url (the canonical public job page), title, description (HTML), locations (list of "City, Region, Country"-style strings), employment_type, date_posted if available, and salary when the source provides it, in the same shape pinpoint uses.
- `async def can_handle(url, client=None, pw=None) -> dict | None`: return `{"tenant": "..."}` when the URL host matches the platform and, if a client is given, the endpoint answers with valid data. Otherwise None.
- `register("<name>", discover, cost=10, can_handle=can_handle, rich=True)`. Use the names `keka`, `greythr`, `zoho_recruit`.

Endpoints:
- **Keka:** `GET https://<tenant>.keka.com/careers/api/jobs/default/active` → JSON list (`id`, `title`, `description`, `jobLocations[{city,state,countryCode}]`, `jobType`, `experience`, `salaryRange{minimum,maximum,currency}`, `publishedOn`). Job URL: `https://<tenant>.keka.com/careers/jobdetails/<id>`. Live tenant for the fixture: `gokwik`.
- **greytHR:** `POST https://<tenant>.greythr.com/hire/api/career/published_jobs/` with JSON body `{}` → `{"data":[{id,title,slug,locations,description,created_at,…}]}`. Job URL: `https://<tenant>.greythr.com/hire/jobs/<slug>`. Live tenant: `greytip`.
- **Zoho Recruit:** `GET https://<tenant>.zohorecruit.com/jobs/Careers` (also `.in` domains) → HTML with `<input type="hidden" id="jobs" value="[...]">` holding HTML-escaped JSON (`id`, `Posting_Title`, `City`, `State`, `Country`, `Job_Type`, `Work_Experience`, `Job_Description` if present). Job URL: `https://<tenant>.zohorecruit.com/jobs/Careers/<id>/<slug-of-title>`. Live tenant: `increff`.

## Tests (no network): `tests/characterization/test_india_ats.py`
- Capture ONE real response per platform from the live tenants above (a single request each; this is the only network you may use), trim it to ≤ 5 jobs, and save it as a fixture.
- Feed each through `discover` via `httpx.MockTransport` (see `tests/characterization/conftest.py` `make_client`). Assert job count, URLs, titles, locations, and salary for Keka.
- `can_handle` positive and negative cases.
- An empty result (`[]` / `{"data":[]}` / no jobs input) returns `[]`.
- A 503 then 200 is retried (use the `sleeps` fixture).

## Acceptance
- `python3 -m pytest -q tests/characterization` passes.
- `python3 -m pytest -q` passes in full.
- Commit in small steps, each message ending with `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed": [...], "tests": "<summary>", "fixture_job_counts": {...}, "unsure": [...]}
