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
- **Budget (raised 2026-11-01, user's 8 GB cap):** `myjobs.slice` gives api, web and three workers 400% CPU and 6.5 GB.
  `myjobs-worker` (browser + sync) keeps its 4.3 GB ceiling; `myjobs-worker-extra@1..2` crawl simple boards only, 1.5 GB
  each, because one Python event loop caps a process (D33). Was: 300% CPU and 5 GB for api, web and one worker.
- **Concurrency (2026-11-01):** 80 coroutines per process, 40 of them for monitors, and a Redis pool of 200. Workers wait
  on the network and per-domain delays, not CPU. 30% of claims, and every claim made while the monitor slots are full,
  take page scrapes first (`claim_work.lua`). Measured: scrapes went from 0 to ~580/min and monitors ran at ~56/min, on
  about 2.6 cores and 3 GB. The CPU package runs 83–96 °C under this load (the throttle point is 100 °C). Postgres and Redis get 1 CPU and about
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

## D36: India-first check intervals (User, 2026-11-01)
- **What:** `src/priority.py` sorts each company by its open tech jobs and sets its boards' check interval in Postgres
  and in the Redis board hash:
  - `india`: any open job is in India or has no resolved location. Keeps the base interval: 1 h, or 3 h for slow types
    (D33).
  - `no_india`: every open job is located, and none is in India. Checked every 12 h.
  - `none`: no open tech jobs. Checked every 8 h.
- **When:** at the end of `sync`, and every 6 h from the simple-worker pipeline, with a Redis lock so only one process
  runs it.
- **Why:** the user asked for India-first crawling. On 2026-11-01 the split was 3,682 / 2,398 / 1,131 boards, so board
  checks fall from about 5,850/h to about 3,000/h, and the freed time goes to page fetches.
- **Trade-off:** when a `no_india` company opens its first India job, it can show up to 12 h late.

## D37: A failing board is never disabled (Default, 2026-11-02)
- **What:** a failed check backs off 5, 10, 20… minutes, capped at a day, and the worker reschedules the board at that
  time. The board stays enabled. After 5 failures in a row and a day without a success, its postings are delisted; they
  come back when a check succeeds again. Only a 404/410 marks a board `gone` (D34); `disabled` now means only removed
  from `data/boards.csv` or turned off in `/admin`.
- **Why:** 5 failures in a row (about 2.5 h of trouble) disabled a board for good, with nothing to retry it. On
  2026-11-02, 337 boards were disabled that way, 188 of them working within the past month. Wipro (6,225 jobs) and
  HCLTech (11,054) were among them, after one `ReadError` midway through their large feeds. They were the two largest
  gaps in the jseek parity run (D28), which found 78.2%.
- **Cost:** a dead board is retried once a day instead of never.

## D38: Undated jobs from a board's first crawl show "date unknown" (User, 2026-11-02)
- **What:** a posting inserted while its board has no successful check in the last 2 days is flagged `backlog`
  (a trigger, migration 0013). With no publish date, its `listed_at` is the epoch: it sorts after every dated job, the
  API sends `listed_at: null`, and the feed shows "date unknown". Once a crawl finds its date, it becomes a normal job.
- **Why:** a first crawl returns the board's whole backlog. Without a date every job looked "just posted": after the
  D37 re-enable, 483 of the newest 500 feed jobs were undated, 315 of them CGI's.
- **Backfill:** only the last 2 days. Older first crawls already sit weeks deep in the feed.
- **Bulk first sightings (2026-11-02):** a check that finds at least 50 new undated jobs, more than a quarter of the
  board's others, marks them `backlog` too (`_MARK_BULK_BACKLOG`). On 2026-11-02, 294 of the top 500 feed jobs were
  undated, NHS posting 350 at once. Migration 0014 applies the rule to the last 7 days, by board and hour.
- **Vague old dates (2026-11-03):** an undated job whose ATS says only "Posted more than 1 month ago" or "30+ days ago"
  (Accenture, Workday) is backlog too: it is old, just not by how much.

## D39: The feed tells a company's post date from a crawl time (User, 2026-11-02)
- **What:** a real post date shows as "● 3 h ago" in green. A job with only our crawler's first sighting shows as
  "○ seen 3 h ago", muted with a dotted underline. A legend sits under the header. Only a real post date gets the
  "fresh" highlight.
- **Why:** 36% of feed jobs had no post date, and the feed showed the crawl time as if it were one. Of the dated jobs
  first seen in the past week, ~77% had been posted more than 7 days earlier, so a crawl time says little about a
  job's age.

## D40: A board is failing only after a day without success (Default, 2026-11-03)
- **What:** health alerts, `myjobs stats` and the coverage page count a board as failing when its last check failed
  **and** it has had no success for 24 h. The admin "failing" list still shows every board whose last check failed.
- **Why:** on 2026-11-03, 597 boards were "failing", but ~230 of them (all 97 Greenhouse, Recruitee, Oracle HCM,
  Workable…) had succeeded within the day: passing timeouts from the laptop, which retry with backoff (D37). They hid
  the real breaks (join's new page layout, mokahr) and fired a false workable alert.

## D41: Stated experience first, then a title estimate; freshers need evidence (User, 2026-11-03)
- **What:** a job's experience is what the posting states (`experience_extract.py`). When it states none, the title's
  level gives an estimate (`ESTIMATE_RULES`: intern 0–1, junior/associate/level I 0–2, II 2–5, III 4–8, senior 5+,
  lead/staff/manager 7+, architect/expert 8+, principal/engineering manager 10+, director 12+). The estimate is worked
  out when the API reads a job, not stored, and the filter applies the same rules as Postgres regexes. The feed shows
  "3–5 yrs" for a stated value and a muted "~0–2 yrs" for an estimate. "Freshers" lists only jobs that state 0 years or
  have an entry-level title. A title too senior for the cap is always out, even when stated years fit. A plain title
  ("Software Engineer") with no stated years has no estimate. We don't guess from the skills list, and we don't run a
  local LLM: the laptop has no RAM to spare (D30), and an LLM can't find years a posting never states.
- **Why:** on 2026-11-03, all 100 of the first India "freshers" jobs had no stated experience, and the list included
  managers, "Engr II" and "Expert" roles. Separately, Redis had lost the scrape tasks for 18k Oracle HCM jobs, so they
  never got a description. A 6-hourly pass now queues those again (`requeue_lost_scrapes`).

## D42: Non-tech role words outrank tech words; CJK titles are judged too (Default, 2026-11-03)
- **What:** in `tech_gate.py`, a title naming a non-tech role (`_NON_TECH_ROLE`: sales, account executive, business
  development, marketing, cashier, retail, security officer/guard, CT/radiology tech, …) is dropped unless it also
  names a tech role (`_TECH_ROLE`: engineer, developer, architect, analyst, scientist, designer, pre-sales, technical
  sales, product manager, ISSO, …). This runs before the taxonomy, which reads "Business Development Manager" as
  engineering-manager. Chinese, Japanese, Korean and Cyrillic titles are kept only with a tech word
  (`_NON_LATIN_TECH_WORDS`: 工程师, 开发, 数据, 项目经理, エンジニア, 개발, инженер, аналитик, …); other non-Latin titles
  (Hebrew, Arabic, Thai…) are still kept unjudged. A trailing ", IT)" is Italy, not the IT department.
- **Why:** on 2026-11-03, about 22% of 400 random feed jobs weren't tech. The biggest groups were CJK titles kept
  unread (16k "星级咖啡师" barista rows, Domino's, Uniqlo, insurance counters), security guards ("security" is a tech
  word), retail "Front End" and "Product Demonstrator" roles, and "Cloud Account Executive" ("cloud" outranked
  account-executive). Re-gating the live rows dropped ~109k of 602k active jobs. On jseek.co's tech sample it keeps 1,146 of
  1,150 postings; the 4 dropped are a sales specialist role. Kept-sample precision went from ~78% to ~95%. The rest is
  a scattered tail (hotel and hospital roles, "Danish Speaker") not worth more patterns.

## D43: A board robots.txt now disallows keeps its schedule but delists its jobs (Default, 2026-11-03)
- **What:** when a site-reading monitor hits a robots.txt `Disallow`, the check is a clean skip (no failure strike), but
  it records `last_checked_at` and the reason in `last_error`, and delists the board's active postings. If robots.txt
  allows us again, the next crawl brings them back. We don't route around a `Disallow` through a different host, even
  when that host has no robots.txt (Goldman's `api-higher.gs.com`).
- **Why:** on 2026-11-03, 18 boards had been skipped this way for days while keeping their old jobs live (Goldman's
  higher.gs.com: 229 jobs from Oct 23), and they looked stuck because nothing was ever written back.

## D44: Delisting guards read their state from the DB and yield to a steady shrink (Default, 2026-11-03)
- **What:** the drop and blast-radius guards read `suspect_streak` and `recent_discovered_counts` from the `job_board`
  row, not the board config the worker caches in Redis. When a guard has skipped gone-detection for 3+ checks over at
  least 24 h and those checks found counts within 10% of each other, gone-detection runs anyway. The streak is kept
  until a check passes normally, so the missing rows can reach their delist threshold.
- **Why:** the cached copy never saw the guard's own writes, so every streak stayed at 1 and every history stayed
  frozen at its sync-time value. A board whose ghost rows outnumbered its live jobs could never delist them. On
  2026-11-03 that left ~37.6k ghost jobs active on the feed (Speechify: 1,499 of 2,237, last seen in May), 98% of them
  undated. A truncating monitor flaps; a board that really shrank reports the same count every check.
