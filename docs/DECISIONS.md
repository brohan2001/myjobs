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
failure (>25%) or emptiness. It exits 1 on any alert. On the laptop, `deploy/laptop/alert.sh` runs it every 15 min and
pushes alerts to a free ntfy.sh topic, sending again only when the set of firing checks changes.

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
is needed only once. Resource limits are in D30. See `docs/DEPLOY.md`.

## D30: myjobs gets 4 of the laptop's 8 threads and 6 GB (User, 2026-10-30)
Uncapped, the worker averaged 3+ cores, peaked at 8.6 GB and kept the CPU at 91 °C. Its ~20 Chromiums also crashed on launch.
- **Budget:** `myjobs.slice` gives api, web and worker 300% CPU and 5 GB together. Postgres and Redis get 1 CPU and about
  1.25 GB in `docker-compose.yml`.
  That is Postgres 768 MB and Redis 512 MB. Redis started with 256 MB, but on 2026-10-31 a scrape backlog of 429k tasks
  got it OOM-killed. The queue now reloads its Lua scripts after a Redis restart.
- **Priorities inside the slice:** the worker has a lower CPU and IO weight and its own 4.3 GB ceiling, so under pressure it
  slows down or restarts and the feed stays up.
- **Why a quota and not pinning:** a quota (`CPUQuota`) still lets the scheduler spread the load across every core.
  Pinning (`AllowedCPUs`) would keep 4 cores pegged and hot.
- **Browser pipeline:** `browser_monitor_concurrency` (6) caps both its coroutines, each of which owns a Playwright driver,
  and its Chromiums.
- **GPU:** the iGPU stays idle because nothing in myjobs can use it.

## D31: The admin side is behind one shared token (Default, 2026-10-30)
- **Pages:** `/admin` uses HTTP Basic auth (user `admin`, password `ADMIN_TOKEN` from `.env`), checked in a Next middleware.
- **API:** the pages call `/api/admin/*` from the server with `Authorization: Bearer $ADMIN_TOKEN`, so the token never
  reaches a browser.
- **No token:** without `ADMIN_TOKEN` set, both the pages and the API return 404.
- **Why the public `/api/v1` stays open:** it serves no user data.
- **Why not real accounts:** there is one operator, so one token is enough.

## D32: Public URL through Cloudflare Tunnel on a free domain (User, 2026-10-30)
- **What:** a Cloudflare Tunnel publishes :3000 under a free DigitalPlat domain (`*.dpdns.org`), with DNS hosted on
  Cloudflare's free plan. `cloudflared` runs as the user unit `myjobs-tunnel`, from a token made in the dashboard, so no
  root is needed.
- **Why not Tailscale Funnel:** it was tried first and dropped. Funnel reached the laptop through relays in Europe and the
  US, so pages took 7–12 s.
- **Why Cloudflare:** its edge has servers in India and ends TLS there. Pages take well under a second, and static assets
  are cached.
- **Exposure:** only the web app is public; the API, Postgres and Redis stay on 127.0.0.1.
- **Fallbacks:** a `workers.dev` Worker with Workers VPC needs no domain, but it is in beta. A paid domain is also possible.
- **Upkeep:** the free domain must be renewed by hand once a year.

## D33: Slow board types are checked every 3 h (User, 2026-10-31)
- **What:** `sync` gives browser boards and the dom, sitemap, icims, workday and api_sniffer types a 180-minute
  check interval. Every other type stays at 60 (`_check_interval` in `src/sync.py`).
- **Why:** the boards restored from jobseek already carried these intervals, but `sync` wrote 60 for every board, so
  the next sync would have made all 2,016 slow boards hourly. Even at 3 h they ran behind: 1,629 boards were more than
  2 h overdue, all of them slow types. The fast API boards were on time.
- **Real bottleneck:** the worker's one Python event loop sat at 100% of a core while the machine was 80% idle. py-spy
  found salary and occupation matching using most of it, and both are now 2–6× faster.
- **Trade-off:** "posted X ago" can be up to 3 h late on slow boards. Most jobs come from the hourly API boards.

## D34: An empty board is never disabled (Default, 2026-10-31)
- **What:** after 6 empty checks a board's postings are delisted, but the board stays enabled as `suspect` and turns
  `active` again when jobs return. Only a 404/410 from the ATS marks a board `gone` and disables it.
- **Why:** 6 empty hourly checks disabled real boards for good. Startups with no openings right now, such as lucidbots
  and striiminc, returned 200 with an empty list. 219 boards had been lost that way, with no rediscovery to bring them
  back. They were re-enabled on 2026-10-31.

## D35: Workday and iCIMS jobs are judged by the title in their URL (Default, 2026-11-01)
- **What:** these ATSs list only URLs, but the URL carries the real title (`…/job/<location>/<Title>_<ReqId>`,
  `…/jobs/<id>/<title>/job`). `drop_at_monitor` now runs the full tech test on that title, so non-tech jobs are never
  stored or queued for a page fetch. Other URL slugs still drop only clearly non-tech roles.
- **Why:** 424k first-time page fetches were queued and growing by about 15k/h. 94% of the queued postings had no title
  yet, only 0.6% were in India, and half came from Workday (Dollar Tree, CVS, Five Below…).
- **Measured on 30k scraped postings:** the URL title drops 99.3% of non-tech jobs and loses 1.2% of tech ones, mostly
  vague slugs like "Manager" with a fuller real title. The strict test would have dropped only 23% of non-tech jobs.
