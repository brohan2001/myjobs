# Handoff: myjobs (2026-10-15)

Branch `revamp/phase-1-feed`, not pushed (ahead of origin). Read `CLAUDE.md`, `docs/REVAMP_PLAN.md` (status and plan),
`docs/DECISIONS.md` (D1–D28), `docs/REPO_MAP.md` and `docs/UPSTREAM.md` first.

## What changed on 2026-10-14/15 (after the user's test pass)
- **Bloat cut (D26):** about 31k lines, including `src/workspace/`, the R2 client, the notice-period feature, the interim
  API page, one-off scripts and finished docs.
- **Crawler scheduling:** the claim order serves board checks before page scrapes. On 2026-10-14, 2,371/2,845 boards were
  >2 h overdue (Google was last checked on Oct 11). Each posting is now scraped once. A second Ctrl-C, or 60 s after the
  first, force-exits the worker. `myjobs boards <company|ats>` shows when a board was last checked.
- **jobseek core re-synced (D28):** 108 monitor types (was 40) at upstream `cf71baa`. Deltas are listed in `docs/UPSTREAM.md`.
- **Tech-only scope (D27):** `src/core/tech_gate.py` keeps 99.1% of tech titles and drops 94.1% of non-tech ones (measured
  on 1,763 jseek-labelled titles).
  - Board checks drop non-tech postings before storing them.
  - URL-only postings get `is_tech` after their scrape.
  - `myjobs apply-tech-gate` applies the rules to stored postings.
- **Posting dates:** migration 0012 adds `posted_at` (the ATS's date) and a generated `listed_at`. The feed sorts and shows
  by `listed_at`, and says "posted" or "first seen".
- **Experience filter:** `≤N years` now also excludes senior titles and seniority tags (freshers also exclude level II).
- **UI:** search runs on Enter; desktop rows are one line on a 1440 px page.
- **Location search:** matches aliases ("bang" → Bengaluru).
- **Portal monitors (D25):** LinkedIn, SEEK and others were added at the user's explicit request.

## Not yet verified against a live database (Docker was off to save RAM)
Migrations 0011–0012, the new SQL (`_SET_POSTED_AT`, `_RECORD_SCRAPE_SUCCESS`, the API `listed_at`/`is_tech` paths),
`apply-tech-gate` and the vendored core inside a running worker. Unit tests (759) pass, and every module imports.

## Next actions, in order
1. Finish the registry vetting: `python scripts/import_upstream_registry.py` (resumable, cache in `output/vetting.jsonl`),
   then `--browser` for the ~440 Playwright boards, then `--apply` to write `data/{companies,boards}.csv`.
2. Remove company-specific monitors that no kept board uses (D27/D28 copy scope). Re-pin
   `tests/characterization/test_registry.py` and list the removed monitors in DECISIONS.
3. Live verification:
   1. `docker compose up -d && alembic upgrade head`.
   2. Purge the old re-scrape backlog: delete the `scrapes_*` Redis keys, and set `next_scrape_at = NULL` where
      `last_scraped_at IS NOT NULL`.
   3. `myjobs sync`, then `myjobs apply-tech-gate`, then `myjobs worker`.
   4. After 2 h: `myjobs health` (no `worker_behind`) and `myjobs boards google`.
4. `python scripts/jseek_parity.py` against the running API; fix causes until in-scope misses are explained.
5. Ship: PR to `main`, then the ₹0 deploy kit (`docs/DEPLOY.md`).

## Open items
- Review queues (deferred by the user): `data/candidates/*/review_queue.csv` via `scripts/triage_review.py`.
- `clari` points at Salesloft's Greenhouse board: confirm the merger or drop it (the upstream import may settle it).
- The later phase (accounts, profiles, tailoring) stays deferred (D10).

## Running locally
`./scripts/dev.sh` (DBs, migrations, worker, API :8090, web :3000), or `--no-worker` to browse without crawling.
Stop a worker with one Ctrl-C (it drains, then force-exits after 60 s) or two (immediate).
