# Handoff: myjobs revamp (2026-10-12)

Branch: `revamp/phase-1-feed` (pushed; `main` is untouched apart from the Phase 0 history purge).
Read `CLAUDE.md`, `docs/REVAMP_PLAN.md` (status table), `docs/DECISIONS.md` (D1–D23) and `docs/REPO_MAP.md` first.

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
  cancel hangs, and `kill -USR1 <pid>` dumps asyncio task stacks.
- **Triage:** `python scripts/triage_review.py <dir> [--open]` walks the review queue (accept / reject / retry with URL /
  skip), resumable via `<dir>/triage.jsonl`. Then `--apply-accepted` the result and feed `retry.csv` back to discovery.
- **Health:** `myjobs health` exits 1 on alerts (D23). On 2026-10-12 it flagged 319 boards marked gone in 24h (the May→October
  ATS churn). Rediscovery pass 2 (`data/candidates/rediscover-2*`) re-found 19 boards; 262 rows wait in the review queues.
- **User-Agent (D14, switched 2026-10-12):** honest `myjobs-bot/0.1` by default. Chrome only for `CHROME_UA_HOSTS` in
  `src/shared/http.py` and for Playwright.
- **Hosting (D24):** must cost ₹0. Plan: one Oracle Always Free VM (`docs/INFRA_PROPOSAL.md` §6).
- **Registry:** 2,914 companies; 77 Indian; 32 verified Indian boards added across discovery passes 1–2.
- **Tests:** about 457 Python tests (no network) and 45 vitest tests.

## Running locally
`docker compose up -d` (Redis host port 6380 in `.env`), then `alembic upgrade head` (now at 0010), then `myjobs worker`.
API: `myjobs serve --port 8090`. Web: `cd web && npm ci && API_ORIGIN=http://127.0.0.1:8090 npm run dev`.
Logs and PIDs are in `~/.myjobs-run/`. Stop processes by PID only (`pkill -f "myjobs worker"` also matches agy prompts).

## Open items (need the user)
1. **Product test:** the user is testing with `docs/TEST_GUIDE.md` (keep / cut / change per feature, plus suspected bloat).
   Cutting and shipping follow from that.
2. **Review queue (deferred by the user):** 294 pass-2 rows (`data/candidates/india-pass2/`) plus pass 1's queue need a human pass with the triage tool.
   Most are company-wide sitemaps that aren't job boards.
3. **Phase 4 deploy:** approve §6 of `docs/INFRA_PROPOSAL.md` (₹0, Oracle Always Free). Needs an Oracle account. The deploy
   scripts (compose services, Caddyfile, backup cron) aren't written yet.
4. **Later phase** (accounts, profiles, per-user scoring, resume tailoring) stays deferred by D10 until the user says go.
5. **GitHub cache:** the scrubbed fixture's old commits may still be reachable by SHA on GitHub until GitHub support purges
   them (backup branches `backup/phase-1-feed-pre-scrub*` are local only and still contain it).
6. Data quality: some registry `company_type` tags are coarse (e.g. Revolut tagged `startup`).

## Working agreement (from the user)
- About 50% of the work goes to agy via `~/.myjobs-run/run_agy.sh <slug> <branch> <model> <brief>` (Gemini 3.8 Flash first).
  Briefs live in `delegation/`. Verify with tests, `git diff --stat` and PII scans; then cherry-pick onto the phase branch.
- agy tends to log structlog-style (`log.info("x", k=v)`); `get_logger` is stdlib, so use `extra={...}`. Check this when merging.
- This session: 3 agy runs (Flash): notice-period extractor, UA A/B script, triage tool.
- Hard rules: no personal data in tracked files; never fabricate resume content; `revamp/*` branches only; respect robots.txt and ToS.
