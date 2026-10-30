# Decisions

Non-obvious choices that still apply. "User" means the user decided; "Default" means Claude chose it and it can be overridden.
Numbers are stable because code cites them; missing numbers were superseded or finished (see git history).

## D1: Postgres + Redis (User, 2026-10-11)
Postgres (asyncpg, alembic migrations) stores everything; Redis holds the work queues, leases and per-domain rate limits.

## D4: We own the jobseek fork (Default, 2026-10-11)
`src/core/` and `src/shared/` come from colophon-group/jobseek (MIT); we may edit them. We change them only through the deltas
in `docs/UPSTREAM.md`, so a re-sync stays a copy plus a short checklist.

## D5: Characterization tests guard scraper changes (Default, 2026-10-11)
`tests/characterization/` pins monitor and scraper outputs, with no network access. Changing a pinned output means updating the snapshot in
the same commit and giving the reason in the message.

## D7: No project licence yet (Default, 2026-10-11)
Choosing one is the user's call. Only the third-party MIT notice is in the repo.

## D8: Local pre-commit PII guard (Default, 2026-10-11)
`.git/hooks/pre-commit` runs gitleaks (`.gitleaks.toml`) and greps staged additions for the patterns in `private/pii_patterns.txt`.
The patterns stay private so the guard itself can't leak the data.

## D10: A public latest-jobs feed first (User, 2026-10-11)
The product is a public jseek.co-style feed for everyone. Per-user profiles, scoring and resume tailoring come later, in their own
tables rather than on `job_posting`.

## D11: Continuous worker (Default, 2026-10-11)
`myjobs worker` runs until SIGTERM. Boards reschedule themselves (`check_interval_minutes`, default 60), and board checks come
before page scrapes. `myjobs crawl` does a single pass.

## D12: Read-only public API with no auth (Default, 2026-10-11)
Nothing served is user data. Controls: per-IP rate limit, capped `limit`, keyset cursors, a 30 s statement timeout, bind
parameters only, nh3-sanitized description HTML, CSP and security headers, and CORS closed unless `API_CORS_ORIGINS` is set.

## D13: GeoNames for locations (Default, 2026-10-11)
`scripts/load_geonames.py` loads countries, admin1 regions, cities15000, Indian aliases and macro regions (EU, APAC…). Country
filters use `location_ids && descendants(country)`, so "Indiana" no longer matches India.

## D14: Honest User-Agent, Chrome for WAF hosts (User, 2026-10-12)
HTTP requests send `myjobs-bot/<ver> (+repo URL)`. `ChromeUAForWAFHostsTransport` (`src/shared/http.py`) swaps in Chrome only
for hosts in `CHROME_UA_HOSTS` (Deloitte, Infosys, L'Oréal, TSMC, Bain, umantis, talentclue). An A/B test on 200 boards lost
0.5% of them with the honest UA. Playwright keeps Chrome's UA.

## D15: Feed design "Field notes" (Default, 2026-10-11)
Atkinson Hyperlegible, sentence-style filters, phone-first. The theme tokens live in one file so the design is cheap to change.

## D16: Next.js (App Router) + TypeScript in `web/`; FastAPI is the API (Default, 2026-10-11)
The feed is server-rendered, and its filters are URL query params, so links can be shared.

## D17: Delegation split (User, 2026-10-11)
About half the work goes to agy (Gemini 3.8 Flash first, then Sonnet 4.6, then Opus 4.6), run with
`--dangerously-skip-permissions`. Delegated work is checked with tests and scope checks (`git diff --stat`), not by reading
every line.

## D21: Company type is a closed list (Default, 2026-10-12)
`company_type` is one of startup, product, mnc, gcc, services, nonprofit or government (`src/company_type.py`). A test keeps
`data/companies.csv` inside the list.

## D23: Health alerts are an exit code (Default, 2026-10-12)
`myjobs health` checks feed staleness (>3 h), worker lag (>5% of boards 2 h overdue), mass board loss (>20 gone a day) and per-ATS
failure (>25%) or emptiness. It exits 1 on any alert.

## D25: Portal monitors are allowed (User, 2026-10-15)
The user wants every jobseek monitor, including job portals whose terms forbid scraping (linkedin, seek, jobstreet, headhunter,
computrabajo, job51, jobbank104, jobs_ch), and accepted that risk. They use the same rate limits and UA as every other
monitor. Naukri has no monitor; ask before adding one.

## D26: Leftover jobseek hooks are no-ops (Default, 2026-10-15)
`src/metrics.py` (Prometheus) and `src/runtime/` (Go fast paths) are stand-ins, so the vendored files stay unmodified.
Migration 0011 dropped the schema nothing used.

## D27: Tech-only scope (User, 2026-10-15)
Only tech-adjacent jobs: software, data/AI, infrastructure/security and product/design, plus TPM, PM, engineering managers, tech
leads, scrum masters, solutions/sales/support engineers, business/quant/data analysts, and electrical, mechanical, automation and
data-center engineers. `src/core/tech_gate.py` drops other postings before they're stored.

## D28: Coverage target is jseek.co parity (User, 2026-10-15)
Every in-scope jseek.co job should appear here too. The registry comes from jobseek's (MIT), vetted for tech, and
`scripts/jseek_parity.py` samples jseek.co and reports misses by cause. New companies are added by re-importing upstream
(`scripts/import_upstream_registry.py`) or with `myjobs company add`.

## D29: Hosted on the user's home laptop for ₹0 (User, 2026-10-30)
The user won't pay for hosting. Everything runs on their old laptop (Ubuntu 26.04, 16 GB RAM, 450 GB disk), not a cloud VM.
Postgres and Redis run in Docker on 127.0.0.1. The API, worker and web app run as systemd user services with linger, so root
is needed only once. The worker is capped at 10 GB because it runs a Chromium per browser board. See `docs/DEPLOY.md`.
