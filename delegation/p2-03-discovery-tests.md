# p2-03-discovery-tests
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-03-discovery-tests` (already checked out)

## Goal
Write a thorough, no-network test suite for `src/discovery/pipeline.py` and `scripts/discover_companies.py`. Read both first. Do NOT modify them. If you find a real bug, add a test marked `@pytest.mark.xfail(strict=True, reason="...")` and list it in your report.

## Files you may touch
- `tests/discovery/__init__.py`, `tests/discovery/test_pipeline.py`, `tests/discovery/test_script.py` (new). Nothing else.

## Cover
1. Pure helpers: `domain_of` (scheme-less input, www stripping, empty input), `slugify`, `unique_slug` (collisions → -2, -3), `is_blocked_host` (naukri.com, www.linkedin.com, sub.indeed.co.in blocked; careers.razorpay.com allowed), `robots_allows` (None → True, Disallow: / → False, a path-specific disallow, an Allow override), `load_candidates` (skips rows without name or website, default country IN), `existing_index`, `registry_rows` (exact dict keys and values; monitor_config JSON-encoded).
2. `evaluate` with monkeypatched network pieces (patch `src.core.monitors.detect_monitor_type`, `src.workspace.career_discover.discover_career_pages`, `src.core.monitor.monitor_one`, `src.core.monitors.monitor_needs_browser`, and `pipeline._fetch_robots`). Cases:
   - an explicit careers_url with a trusted monitor and jobs → accepted;
   - a trusted monitor with 0 jobs → review;
   - an untrusted monitor (sitemap) with 300 URLs → review with "generic monitor";
   - a browser-only monitor → review;
   - robots disallow → rejected;
   - discovery raising → review with "discovery error";
   - homepage discovery picking the highest-score candidate and skipping blocked hosts.

   Use a fake `httpx.AsyncClient` built with `httpx.MockTransport` for the homepage fetch.
3. `run` with `evaluate` monkeypatched: duplicates by domain against the registry, duplicates within the batch, blocked portal → rejected, a per-company timeout → review, and an accepted board whose URL already exists → duplicate. Patch `src.shared.http.create_http_client` to return a MockTransport client.
4. Script: run `main([...])` on a tmp candidates CSV with `pipeline.run` monkeypatched to return canned outcomes. Monkeypatch the script's `DATA` to a tmp dir holding small companies.csv/boards.csv. Assert review_queue.csv and discovery_report.json contents, and that `--apply` appends rows (tag columns added to the header, unique slugs).

Tests must never touch the network. Add an autouse fixture in `tests/discovery/conftest.py` (also allowed) that makes `socket.socket.connect` raise.

## Acceptance
- `python3 -m pytest -q tests/discovery` passes.
- `python3 -m pytest -q --ignore=tests/test_salary_inr.py` passes in full.
- Commit with message `test: discovery pipeline suite` and the line `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed": [...], "tests": "<pytest summary>", "bugs_found": [...], "unsure": [...]}
