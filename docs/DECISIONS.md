# Decisions

Each entry records a non-obvious choice and its reason. Newest at the bottom. "User" means the user decided; "Default" means the orchestrator chose it and it can be overridden.

## D1: Postgres + Redis are the baseline (User, 2026-10-11)
The code had already been ported to Postgres + Redis + alembic. We keep that instead of the brief's "SQLite behind a repository"
assumption. Repository interfaces still wrap persistence (Phase 1.3). The legacy SQLite `jobs.db` is used only for the historical baseline.

## D2: Purge personal data from git history (User, 2026-10-11)
The repo is public and had resumes, email and visa status tracked since the first commit. We ran `git filter-repo` path removal plus string
replacement and force-pushed `main` once (the only time `main` is touched). A mirror backup is kept outside the repo. See AUDIT §10 for residual risk.

## D3: Auto-push Stop hook disabled during the revamp (User, 2026-10-11)
It ran `git add -A && commit && push` on any branch, which conflicts with per-phase branches and small commits. We removed it from
`.claude/settings.json` (local, gitignored). The script stays in `.claude/hooks/` for re-enabling later.

## D4: We own the jobseek fork (Default, 2026-10-11)
`src/core/` and `src/shared/` come from colophon-group/jobseek (MIT). The old "vendored, do not edit" rule is dropped: we will change monitors
(politeness, India ATS, bug fixes). Attribution is in `THIRD_PARTY_NOTICES.md`. Fork point: commits `fa17282` (Monitor→Scraper port) and `2dceb26` (Postgres + Redis port), post-rewrite SHAs. The upstream jobseek commit isn't recorded; Phase 2B should pin it by diffing against upstream.

## D5: Characterization tests before any scraper change (Default, 2026-10-11)
`tests/characterization/` pins current monitor and scraper outputs with no network. Changing a pinned output requires updating the
snapshot in the same commit with a reason in the message.

## D6: Politeness posture (Default, pending user answer to Q1)
Proposed: honest identifying UA, honor robots.txt for permission, honor `Retry-After`, stealth and proxy off by default. Boards that
become blocked are quarantined and reported rather than silently dropped.

## D7: No root LICENSE chosen yet (Default, 2026-10-11)
Choosing the project's own license is the user's call (open question). Only the third-party MIT notice was added.

## D8: Local pre-commit PII guard (Default, 2026-10-11)
`.git/hooks/pre-commit` runs gitleaks (`.gitleaks.toml`) and greps staged additions for patterns in `private/pii_patterns.txt`.
Patterns stay private so the guard itself doesn't leak the data. Not enforced in CI yet (Phase 4).

## D9: Phase 0 WIP committed as a snapshot, not fixed (Default, 2026-10-11)
The uncommitted server/UI work and migration 0008 were committed unchanged on `revamp/phase-0-audit`, so the baseline matches the code
that produced it. Its bugs are listed in AUDIT §4 and §8.

## D10: Pivot to a public latest-jobs feed first (User, 2026-10-11)
The user asked to drop the daily reports, shortlist and AI resume tooling and to focus on serving the latest jobs to everyone,
jseek.co-style. Deleted: ranker/scoring, HTML report, Claude generator, visa/H1B data and columns (migration 0009), the `crawler`
entry point. Per-user profiles, scoring and resume tailoring move to a later phase and will live in their own tables, not on
`job_posting`. Supersedes most of REVAMP_PLAN Phase 1 and the visa part of Phase 2A.

## D11: Continuous worker instead of daily runs (Default, 2026-10-11)
`myjobs worker` runs the pipeline until SIGTERM. Boards reschedule themselves (`check_interval_minutes`, default 60) and
URL-only postings are re-scraped on `scrape_interval_hours`. `myjobs crawl` keeps a one-pass mode for dev/cron. Freshness is
exposed as `/api/v1/stats.last_updated`.

## D12: Public API is read-only with no auth; abuse is bounded by design (Default, 2026-10-11)
Nothing served is user data. Controls: per-IP fixed-window rate limit (Redis, falling back to in-process), capped `limit`, keyset
cursors (no deep OFFSET scans), the 30 s DB statement timeout, all filters as bind parameters, third-party description HTML
sanitized with nh3, CSP and security headers, CORS closed unless `API_CORS_ORIGINS` is set. `/api/refresh` was removed.

## D13: GeoNames for locations (Default, 2026-10-11)
`scripts/load_geonames.py` loads countryInfo, admin1 and cities15000 (CC-BY 4.0, attributed) plus Indian alias fixes and macro regions
(EU, EMEA, APAC, LATAM…). Country filtering uses `location_ids && descendants(country)` with an in-memory index in the API. This replaces
the substring country matching that turned "Indiana" into India.

## D14: Honest User-Agent by default, Chrome for WAF hosts (User, 2026-10-12; revises D6)
Upstream switched from an identifying UA to a Chrome UA after WAF blocks on several big employer career sites, including Infosys
(`src/shared/http.py:41`). Switching back blind could silently cost India-relevant coverage. Plan: A/B a sample of ~200 boards with
an honest UA in Phase 2B, then decide with data. robots.txt permission checks (2B.1) are independent of this and still planned.

**A/B result (2026-10-12, `scripts/ua_ab_test.py`, 200 non-browser boards, 100 API + 100 site):** 187 same, 1 honest-blocked
(i2cat on talentclue: 7 jobs with Chrome, 0 with the honest UA), 12 failed under both UAs, 0 honest-fewer. Data in
the A/B run's report (in git history before 2026-10-15). The honest UA costs 0.5% of working boards, but the WAF-protected hosts that
prompted upstream's switch (Infosys, Deloitte, L'Oréal, Bain, umantis) were not in the sample. Recommendation: switch the
default to `myjobs-bot/<ver> (+repo URL)` with a Chrome-UA allowlist for those hosts.

**Switched (user, 2026-10-12):** `DEFAULT_USER_AGENT` in `src/shared/http.py` is now `HONEST_USER_AGENT`.
`ChromeUAForWAFHostsTransport` swaps in Chrome per request (and per redirect hop) for hosts in `CHROME_UA_HOSTS` (Deloitte,
Infosys, L'Oréal, TSMC, Bain, `*.umantis.com`, `*.talentclue.com`), and only when the request still carries the default UA.
The Playwright browser UA (`src/shared/browser.py`) stays Chrome: the A/B covered non-browser boards only.

## D15: Feed design direction C, "Field notes" (Default, 2026-10-11; user may override)
Picked while the user was away and had asked for autonomous progress. Reasons: the strongest phone layout of the three (the first
job sits above the fold at 375 px), the most legible face (Atkinson Hyperlegible) for a mobile, India-first audience, and
sentence-style filters that are distinctive without being gimmicky. A (Ledger) is the fallback; the frontend keeps tokens in one
theme file so a switch is cheap.

## D16: Frontend stack: Next.js (App Router) + TypeScript in web/, FastAPI stays the API (Default, 2026-10-11)
The user is comfortable with Next.js. The feed list is server-rendered for fast first paint on slow connections, and filters are URL
query params, so links are shareable. The Python worker and API are unchanged.

## D17: Delegation split (User, 2026-10-11)
About 50% of the work goes to agy (Gemini 3.8 Flash first, then Sonnet 4.6, then Opus 4.6), run with --dangerously-skip-permissions.
Delegated work is verified by contract tests, scope checks (`git diff --stat`) and structured reports, not by line-by-line reading.

## D18: Discovery auto-accept rules (Default, 2026-10-11)
A board enters the registry without human review only when (a) an ATS API monitor (`API_MONITORS`) parses at least one job,
or (b) a generic sitemap/DOM/nextdata detector finds URLs and at least 2 of 3 sampled URLs carry schema.org JobPosting
JSON-LD (scraped with `json-ld`). Everything else, including browser-only boards, goes to `data/candidates/*/review_queue.csv`.
Job portals whose ToS forbid scraping (`BLOCKED_HOSTS`) are rejected outright.

## D19: Indian ATS adapters: Keka, greytHR, Zoho Recruit (Default, 2026-10-11)
Chosen from docs/research/INDIA_ATS.md, with all three public endpoints verified live (no auth). Darwinbox, Taleo and iCIMS have no public
endpoint, so they fall back to the DOM, sitemap or JSON-LD monitors instead of private APIs.

## D20: Docker Desktop stops observed (2026-10-11)
Docker Desktop quit four times during the session through its own GUI quit path (`POST /app/quit` in the backend log). The cause
is unknown and nothing in the repo triggers it. Postgres data survives in the `pgdata` volume; Redis queues are rebuilt by
`myjobs worker` (which syncs on start). agy briefs now forbid touching Docker. For deployment, run Postgres and Redis as system
services, not Docker Desktop.

## D21: Company-type taxonomy is a closed list (Default, 2026-10-12)
`company_type` is one of startup, product, mnc, gcc, services, nonprofit, government (`src/company_type.py`). Unicorn and funded
startups fold into `startup`, `mnc_gcc` into `gcc`. Discovery normalizes candidate categories and drops anything else (industry
labels like "fintech" are not company types). A test keeps `data/companies.csv` inside the list. The API filter is
`company_type=startup,gcc` (any of).

## D22: Notice period is filled out-of-band (Default, 2026-10-12; superseded by D26)
`job_posting.notice_max_days` (migration 0010) is written by a loop inside `myjobs worker` (`src/processing/notice.py`)
that re-parses a posting whenever its description hash changes. The monitor and scrape writers use positional SQL in four
places; threading a new column through all of them risked silent misalignment for a field that only ~0.03% of postings
state. The API filter `notice_days=N` keeps postings that accept at least N days *or don't say*, so the filter never hides
the silent majority.

## D23: Health alerts are a CLI exit code (Default, 2026-10-12)
`myjobs health` (`src/health.py`) checks feed staleness (>3h), worker lag (>5% of boards 2h overdue), mass board loss
(>20 gone/day), and per-ATS failure (>25%) or emptiness (>30% with no jobs for 3 days, ATS types with ≥5 boards). It
exits 1 on any alert, so cron/systemd can notify. No webhook until deployment picks a channel (Phase 4).

## D24: Hosting costs ₹0 (User, 2026-10-12)
The user won't pay for hosting. The plan is one Oracle Cloud Always Free A1 VM for everything: Postgres, Redis, worker, API, the
Next.js web app and Caddy. A free DuckDNS hostname, Let's Encrypt, backups in Oracle Object Storage and the Healthchecks.io free
tier complete the setup (`docs/DEPLOY.md`). Free managed Postgres tiers can't hold the 2.8 GB database, and running
the web app on the same VM avoids the Cloudflare/OpenNext adapter (Vercel's free plan bars commercial use). Never upgrade the
Oracle account to Pay-As-You-Go.

## D25: Portal monitors are allowed (User, 2026-10-15; replaces the portal part of the hard rule)
The user asked for every jobseek monitor, including those that read job portals rather than company career sites: linkedin,
seek, jobstreet, headhunter, computrabajo, job51, jobbank104 and jobs_ch. Their terms of service forbid scraping, and LinkedIn is
known to sue scrapers; the user was told this and accepted the risk. They run through the same per-domain rate limits and honest
User-Agent as every other monitor. Naukri still has no monitor.

## D26: Cut list from the 2026-10-14 test pass (User, 2026-10-15)
Removed:
- `src/workspace/` (jobseek's workspace CLI);
- the R2 client (only `content_hash` survives, in `src/core/hashing.py`);
- the notice-period feature (0% of postings had a value);
- the interim API page and the one-off scripts (build_csvs, fix_workday_sites, probe_jobseek_monitors, ua_ab_test, baseline_snapshot);
- design mockups, finished delegation briefs, baseline snapshots, AUDIT and SCRAPING_REPORT, and the paid-hosting survey.

Migration 0011 drops the notice columns and jobseek's `indexnow_submission`/`exporter_state` tables. `src/metrics.py` goes
when the core is re-synced with upstream, since upstream's core calls it in many places.

## D27: Tech-only scope (User, 2026-10-15)
The feed covers tech-adjacent jobs only, and non-tech postings are dropped before they're fetched or stored.

Tech means the occupation domains software-engineering, data-ai, infrastructure-security and product-design, plus:
- PM and management: TPM, project manager, engineering manager, tech lead, scrum master;
- sales and support engineering: solutions architect, sales/customer/support engineer;
- analysts: business, quant and data analysts;
- hardware: electrical, mechanical and automation engineers, data-center roles.

A company stays in the registry only while it has at least one tech posting.

## D28: Parity target is jseek.co (User, 2026-10-15)
Every in-scope jseek.co job should also appear here. Coverage comes from importing jobseek's registry
(`apps/crawler/data/{companies,boards}.csv`, MIT) and porting its monitors. A parity script samples jseek.co's public
`/api/v1/search` and reports misses by cause.

