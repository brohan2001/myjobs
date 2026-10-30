# Vendored jobseek core

`src/core/monitors/`, `src/core/scrapers/` and the modules they import are copied from
[colophon-group/jobseek](https://github.com/colophon-group/jobseek) `apps/crawler/src/` (MIT) at
commit `cf71baa66147eb825c9569bfa70be87be7e92c91` (2026-10-14). Treat them as a library: change
them only through the deltas below, so re-syncing stays a copy plus a short checklist.

## What is vendored
- `src/core/monitors/*`, `src/core/scrapers/*`
- `src/core/{monitor,scrape,adp,enum_normalize,job_content,jsonld}.py`
- `src/core/static_registry.py` (upstream `src/workspace/_compat.py`)
- `src/shared/*`, except `robots.py` (ours) and `langdetect.py`/`logging.py` (from the May fork)

Ours, not vendored: `src/core/*_resolve.py`, `salary_extract.py` (+ `salary_inr.py`), `experience_extract.py`,
`location_resolve.py`, `tech_gate.py`, `hashing.py`, and everything in `src/processing`, `src/workers`,
`src/queries`, `src/lua`.

## Deltas to re-apply after a copy
1. `src/shared/http.py`: honest User-Agent plus `CHROME_UA_HOSTS` and `ChromeUAForWAFHostsTransport`, wrapped
   inside `RequestHostTrackingTransport` (D14). Marked `myjobs delta`.
2. `src/core/monitors/brassring.py`: selectolax's `LexborHTMLParser`, not `selectolax.parser` (removed in selectolax 1.x).
3. `src/config.py` must provide the settings the vendored code reads (`webshare_proxy_urls`,
   `webshare_proxy_canary_slot`, …).

Stand-ins, so vendored files stay unmodified:
- `src/runtime/__init__.py` reports jobseek's Go fast paths as disabled.
- `src/metrics.py` turns every Prometheus metric into a no-op (D26).

## Re-sync checklist
1. Copy the files above from a new upstream commit; update the SHA here and in `THIRD_PARTY_NOTICES.md`.
2. Re-apply the deltas; add any new settings or dependencies the copy needs.
3. Run `python3 -m pytest -q`:
   - `tests/test_static_registry.py` catches registry drift;
   - re-pin `tests/characterization/test_registry.py` deliberately (D5).
4. Delete monitors and scrapers no board in `data/boards.csv` uses, with their registry entries and tests.
