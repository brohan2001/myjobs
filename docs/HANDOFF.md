# Handoff: myjobs revamp (2026-10-12)

Branch: `revamp/phase-1-feed`. **The 2026-10-12 afternoon commits are local only; run `git push` to publish them.** `main` is
untouched apart from the Phase 0 history purge.
Read `CLAUDE.md`, `docs/REVAMP_PLAN.md` (status table), `docs/DECISIONS.md` (D1–D24) and `docs/REPO_MAP.md` first.

## What exists now
**Product:** a public, read-only feed of the latest jobs from ~3,200 company career boards, worldwide, with India as the
default lens. No user accounts yet (D10).

- **Crawler:** `myjobs worker` re-checks every board about hourly, browser boards included. Per-domain rate limits, SSRF
  guard, robots.txt for site-reading monitors. A notice-period loop runs beside it (D22).
- **API:** `/api/v1/jobs` filters: q, country/macro, location, company, work_mode, since, seniority, occupation, max_years,
  `company_type` (comma-separated, D21), `notice_days` (D22); keyset cursor. Jobs carry `company.type` and `notice_max_days`.
- **Frontend (`web/`):** sentence filters for place, work mode, company type, experience, notice period and time window;
  INR display, company-run collapsing, detail and coverage pages.
- **Discovery:** `scripts/discover_companies.py` (candidate → board → registry or review queue). Hardened on 2026-10-12:
  browser closes are time-bounded, a site's exception no longer aborts the batch, the watchdog exits for `--resume` if a
  cancel hangs, `kill -USR1 <pid>` dumps asyncio task stacks, and each company gets its own HTTP client (a shared pool
  leaked connections and made 99 of 177 companies fail with PoolTimeout).
- **Triage:** `python scripts/triage_review.py <dir> [--open]` walks the review queue (accept / reject / retry with URL /
  skip), resumable via `<dir>/triage.jsonl`. Then `--apply-accepted` the result and feed `retry.csv` back to discovery.
- **Health:** `myjobs health` exits 1 on alerts (D23). On 2026-10-12 it flagged 319 boards marked gone in 24h (the May→October
  ATS churn). Rediscovery pass 2 (`data/candidates/rediscover-2*`) re-found 19 boards; 262 rows wait in the review queues.
- **User-Agent (D14, switched 2026-10-12):** honest `myjobs-bot/0.1` by default. Chrome only for `CHROME_UA_HOSTS` in
  `src/shared/http.py` and for Playwright.
- **Hosting (D24):** must cost ₹0. Plan: one Oracle Always Free VM (`docs/INFRA_PROPOSAL.md` §6).
- **Registry:** 2,914 companies (77 Indian) and 2,845 active boards; 32 verified Indian boards added across discovery passes 1–2.
  `company_type` audited by agy (22 fixes, `docs/research/company_type_audit.md`); it was conservative, so coarse tags remain.
- **Tests:** 469 Python tests (no network) and 45 vitest tests, all green.

## Running locally
`docker compose up -d` (Redis host port 6380 in `.env`), then `alembic upgrade head` (now at 0010), then `myjobs worker`.
API: `myjobs serve --port 8090`. Web: `cd web && npm ci && API_ORIGIN=http://127.0.0.1:8090 npm run dev`.
Logs and PIDs are in `~/.myjobs-run/`. Stop processes by PID only (`pkill -f "myjobs worker"` also matches agy prompts).

## Session log, 2026-10-12 afternoon (commits ea81738..d195e93)
1. Honest User-Agent with a Chrome allowlist (D14): `src/shared/http.py`, `tests/test_http_ua.py`.
2. Free hosting plan (D24): `docs/INFRA_PROPOSAL.md` §6.
3. `docs/TEST_GUIDE.md`: a keep / cut / change checklist covering 37 features, plus 6 suspected-bloat items.
4. Discovery fix: one HTTP client per company (`src/discovery/pipeline.py`).
5. Rediscovery pass 2: +19 boards (389 jobs) in `data/boards.csv`. Inputs and queues in `data/candidates/rediscover-2*`.
6. company_type audit (agy, Flash): 22 changes merged.
7. Worker restarted on the new code (PID in `~/.myjobs-run/worker.pid`). API on :8090 and web on :3000 are still running.

## Next actions, in order
1. **User tests the product** with `docs/TEST_GUIDE.md` and fills in the Verdict columns. Wait for that before cutting
   anything.
2. **Apply the verdicts:** delete the "cut" items, starting with the biggest suspected bloat. Most of `src/workspace/`
   (about 17k lines) is fork leftovers; only `career_discover.py` and `_compat.py` are imported from outside it, so check
   their transitive imports first. Keep the characterization tests green.
3. **Ship:** open a PR from `revamp/phase-1-feed` to `main`. Then write the ₹0 deploy kit from INFRA_PROPOSAL §6:
   - production compose services for the worker, API, `web` (`next start`) and Caddy;
   - a Caddyfile (`/` to Next.js, `/api` to FastAPI);
   - a nightly `pg_dump` to Oracle Object Storage;
   - a Healthchecks.io ping on `myjobs health`.
   The user then creates the Oracle account (a card for verification only; never upgrade to Pay-As-You-Go) and a DuckDNS
   name.
4. **Check before shipping:** `clari` was rediscovered onto Salesloft's Greenhouse board (`token: salesloft`). Confirm the
   Clari–Salesloft merger, or remove that row from `data/boards.csv`.

## Open items
1. **Review queues (deferred by the user):**
   - `data/candidates/india-pass2/` (294 rows) and pass 1's queue;
   - `data/candidates/rediscover-2*/review_queue.csv` (262 rows: mostly sitemap and DOM hits, with 403s from WAFs).
   Use `scripts/triage_review.py`.
2. **Later phase** (accounts, profiles, per-user scoring, resume tailoring) stays deferred by D10 until the user says go.
3. **GitHub cache:** the scrubbed fixture's old commits may still be reachable by SHA on GitHub until GitHub support purges
   them (backup branches `backup/phase-1-feed-pre-scrub*` are local only and still contain it).
4. **Coarse `company_type` tags remain.** Sports teams were tagged `product` because nothing in the closed list fits them.
5. `myjobs health` shows the "319 gone in 24h" alert until those boards are more than 24h past their gone time. It clears
   on its own.

## Working agreement (from the user)
- About 50% of the work goes to agy via `~/.myjobs-run/run_agy.sh <slug> <branch> <model> <brief>` (Gemini 3.8 Flash first).
  Briefs live in `delegation/`. Verify with tests, `git diff --stat` and PII scans; then cherry-pick onto the phase branch.
- agy tends to log structlog-style (`log.info("x", k=v)`); `get_logger` is stdlib, so use `extra={...}`. Check this when merging.
- agy runs so far (Flash): notice-period extractor, UA A/B script, triage tool, company_type audit (p2-10).
- The user won't pay for hosting (D24). Free tiers only.
- Hard rules: no personal data in tracked files; never fabricate resume content; `revamp/*` branches only; respect robots.txt and ToS.
