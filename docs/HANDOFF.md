# Handoff: myjobs revamp (2026-10-11)

Branch: `revamp/phase-1-feed` (pushed; `main` is untouched apart from the Phase 0 history purge).
Read `CLAUDE.md`, `docs/REVAMP_PLAN.md` (status table), `docs/DECISIONS.md` (D1–D20) and `docs/REPO_MAP.md` first.

## What exists now
**Product:** a public, read-only feed of the latest jobs from ~3,200 company career boards, worldwide, with India as the default lens (jseek.co-style). No user accounts yet.

- **Crawler:** `myjobs worker` runs continuously. Every board re-checks itself about hourly, browser boards included.
  - Per-domain rate limits.
  - SSRF guard on all fetches. This was previously bypassed; now fixed.
  - robots.txt is honoured for site-reading monitors (`src/shared/robots.py`).
  - Fixes: Workday error swallowing, the half-wired `locations_raw` WIP, and concurrency tuned for a single instance.
- **Removed:** daily reports, shortlist scoring, the AI resume generator, and all visa/H1B code and data (migration 0009).
- **Locations:** GeoNames loader (`scripts/load_geonames.py`) with Indian aliases (Bangalore→Bengaluru, Gurgaon→Gurugram, …) and ASCII Indian names.
- **Salary:** INR/LPA/lakh/crore parsing (`src/core/salary_inr.py`), wired into the salary extractor.
- **API (FastAPI, `src/api/`):** `/api/v1/jobs` (filters: q, country/macro, location, company, work_mode, since, seniority, occupation, max_years; keyset cursor), plus `/jobs/{id}` with sanitized HTML, `/companies`, `/locations`, `/stats` and `/coverage`.
  - Rate limit, CSP and security headers.
  - Hides untitled postings and non-jobs ("talent community", "general application").
- **Frontend (`web/`, Next.js + TS, design C "Field notes"):**
  - Server-rendered feed with sentence-style filters.
  - INR/LPA display with currency switch.
  - Location relevance, ATS labels, collapsing of runs from one company.
  - Job detail page and `/coverage` page. Light/dark themes, keyboard navigation.
- **Discovery (`src/discovery/`, `scripts/discover_companies.py`):** candidate company → careers board → ATS detection → robots check → parse validation → registry or review queue.
  - Auto-accepts only ATS-API boards, or generic boards whose sampled pages carry JobPosting JSON-LD.
  - `--rediscover`, `--apply-accepted`, `--resume`; journals outcomes to `outcomes.jsonl`; idle watchdog.
- **Indian ATS adapters:** Keka, greytHR and Zoho Recruit monitors (endpoints verified live).
- **Registry:**
  - 2,882 companies tagged with HQ country, city and type.
  - 73 Indian companies, up from about 8. 28 verified Indian boards (~11k jobs) added.
  - 30 boards recovered for companies whose ATS changed since May.
- **Docs:** AUDIT, SCRAPING_REPORT, REVAMP_PLAN, DECISIONS, REPO_MAP, INFRA_PROPOSAL (Phase 4 draft), JSEEK_INTEGRATION (Phase 5 draft), research/INDIA_ATS.md, research/INDIA_COMPANY_SOURCES.md, README, DESIGN_BRIEF, design/mockups/.
- **Tests:** about 365 Python tests (no network) and 44 vitest tests.

## Running locally
`docker compose up -d` (Redis host port 6380 is set in `.env`, because another project uses 6379), then `alembic upgrade head`, then `myjobs worker`.
For the API, `myjobs serve --port 8090`. For the frontend, `cd web && npm install && API_ORIGIN=http://127.0.0.1:8090 npm run dev`.
Runtime logs and PIDs are in `~/.myjobs-run/`. Stop processes by PID only: `pkill -f "myjobs worker"` also matches agy prompts.

## Open items (in priority order)
1. **History redaction needs the user's approval.** Older commits on `revamp/phase-1-feed` contain one fixture
   (`tests/characterization/fixtures/greythr_greytip.json`) with a greytHR recruiter's name and work email. The current files are scrubbed.
   - Fix: back up the branch, run `git filter-repo --refs revamp/phase-1-feed --replace-text ~/.myjobs-run/scrub.txt`, then force-push this branch only.
   - The auto-mode classifier blocked this as destructive, so it needs explicit permission.
2. **India pass-2 discovery** (298 review-queue companies) was running in the background. Output: `data/candidates/india-pass2/`.
   - Resume if needed: `python scripts/discover_companies.py ~/.myjobs-run/india_pass2.csv --resume --out-dir data/candidates/india-pass2`.
   - Then apply: `python scripts/discover_companies.py data/candidates/india-pass2/accepted.csv --apply-accepted`.
   - Then commit and restart the worker so it syncs the new boards.
3. Re-run discovery for candidates on Keka, greytHR or Zoho hosts (the adapters were merged after pass 1), and for 52 Darwinbox/Freshteam/other boards using the DOM or JSON-LD fallback.
4. `.gitignore` has a stray `d` at the end, probably an editor keystroke. Remove it.
5. **Docker Desktop quit itself four times** (`POST /app/quit` in its backend log). The cause is unknown; see D20.
6. **Next features:**
   - A/B test an honest User-Agent on ~200 boards (D14).
   - Notice-period and company-type filters in the API and UI.
   - Review-queue triage UI.
   - Browser-worker scheduling for deployment.
   - Phase 4 deploy after the user approves `docs/INFRA_PROPOSAL.md`.
   - Later: user accounts, profiles, per-user scoring and resume tailoring (D10).

## Working agreement (from the user)
- About 50% of the work is delegated to agy via `~/.myjobs-run/run_agy.sh <slug> <branch> <model> <brief>`, with Gemini 3.8 Flash first, then Sonnet 4.6, then Opus 4.6, always with `--dangerously-skip-permissions`.
- Briefs live in `delegation/`. Verify agy output with tests, `git diff --stat` and PII scans, not by reading code.
- Scan agy fixtures for third-party personal data **before** merging and pushing (the lesson from item 1).
- This session used 13 agy runs: 12 Flash, 1 Sonnet 4.6.
- Hard rules: no personal data in tracked files; never fabricate resume content; work on `revamp/*` branches only; respect robots.txt and ToS.
