# myjobs — Job Application Automation System

## What this project does

Daily pipeline that:
1. Scrapes job listings from 98 active target companies across 14 ATS types
2. Parses visa signals, role category, and experience requirements from each job
3. Scores every job on 5 factors (skill match, role priority, visa, recency, company tier)
4. Shortlists the top 50 and renders a ranked HTML report + live web UI

**Phase 2 (not yet built):** Claude API-based resume and cover letter generation per job.

---

## Candidate profile

- **Name:** the candidate
- **Email:** candidate@example.com
- **Education:** MS Computer Science, [university] (May 2025)
- **Visa:** [redacted]
- **Published research:** IJCNLP-AACL 2025 (constrained LLM text generation, [lab])
- **Target roles (priority order):** Backend SWE > Cloud Engineer > Fullstack SWE > Frontend SWE > Mobile > Network Engineer > Data Scientist > ML Engineer

### Resume files (in `Resume/`)

| File | Used for |
|------|----------|
| `resume_SWE.pdf` | Backend, Frontend, Fullstack, Mobile |
| `resume_Cloud.pdf` | Cloud, DevOps, SRE |
| `resume_Network.pdf` | Network Engineer |
| `resume_DS.pdf` | Data Scientist |
| `resume_ML_Publication.pdf` | ML Engineer, AI Researcher |

---

## Running the system

```bash
# Install (once)
pip install -e .

# Full daily run: scrape → parse → rank → shortlist → report
myjobs run

# Show top 20 jobs in terminal
myjobs show --top 20

# Filter flags for show command
myjobs show --us-only          # US/remote only
myjobs show --new-grad         # entry-level / ≤2 yrs exp only
myjobs show --role backend     # filter by role category

# Live web UI (http://localhost:8080)
myjobs serve

# Open today's HTML report in browser
myjobs open-report

# Mark a job as applied
myjobs apply <job_id>

# Application history
myjobs history --days 30

# Stats
myjobs stats

# H1-B data management
myjobs update-h1b              # sync H1-B petition counts from data/h1b_sponsors.json

# API key smoke test
myjobs verify-api

# Company management
myjobs company list
myjobs company add --name "Stripe" --slug stripe --ats greenhouse --tier 1
myjobs company disable old-company

# Scraper health check
python scripts/check_scrapers.py          # uses cached results
python scripts/check_scrapers.py --fresh  # re-test all companies

# Workday URL auto-discovery
python scripts/discover_workday_urls.py          # dry-run
python scripts/discover_workday_urls.py --apply  # patch companies.json
```

---

## Key files

| File | Purpose |
|------|---------|
| `src/config.py` | Skill groups, role weights, score weights — edit here to tune ranking |
| `src/ranker.py` | All 5 scoring functions + signal parsing |
| `src/pipeline.py` | Orchestrates the full daily run (scrape → enrich → parse → rank → shortlist → render) |
| `src/logger.py` | Structured JSON logger (`get_logger(name)`) + event helpers; emits to stderr |
| `src/utils/retry.py` | `async_retry()` — exponential backoff + jitter, Retry-After support |
| `src/scrapers/base.py` | `BaseScraper` ABC; `_request()` uses `async_retry` internally |
| `src/scrapers/greenhouse.py` | Greenhouse public JSON API client |
| `src/scrapers/lever.py` | Lever public JSON API client (paginated, cap 500) |
| `src/scrapers/workday.py` | Workday POST pagination API with curl_cffi Chrome impersonation; descriptions fetched separately |
| `src/scrapers/amazon.py` | Amazon Jobs search JSON API (handles both old `hits:[]` and new `hits:N,jobs:[]` formats) |
| `src/scrapers/google.py` | Google Careers Playwright-based scraper |
| `src/scrapers/apple.py` | Apple Jobs public API with curl_cffi fallback |
| `src/scrapers/linkedin.py` | LinkedIn per-company (blocked by login wall) + broad keyword search |
| `src/scrapers/ashby.py` | Ashby public posting API (rate_limit_rps=2.0, max 5 detail fetches) |
| `src/scrapers/microsoft.py` | Microsoft Careers JSON API |
| `src/scrapers/workable.py` | Workable public jobs API |
| `src/scrapers/rippling.py` | Rippling public jobs board |
| `src/scrapers/smartrecruiters.py` | SmartRecruiters public API |
| `src/scrapers/avature.py` | Avature ATS REST scraper (Bloomberg); paginated, cap 300 |
| `src/scrapers/oracle_cloud.py` | Oracle Recruiting Cloud finder-param API (JPMC, AmEx); paginated, cap 300 |
| `src/scrapers/serp_fallback.py` | DuckDuckGo text search via `ddgs` package (Meta, Coinbase, Retool) |
| `src/server.py` | FastAPI live web UI (`myjobs serve`) |
| `src/renderer.py` | Jinja2 → HTML daily report |
| `src/database.py` | SQLite schema + all query helpers; H1-B data; US location detection |
| `src/cli.py` | Typer CLI (all user-facing commands) |
| `data/companies.json` | 102 companies total (98 active, 4 disabled) with ATS config |
| `data/h1b_sponsors.json` | USCIS H1-B petition counts for 54 companies (FY2022–2024) |
| `data/visa_keywords.json` | Visa positive/negative signal phrases |
| `data/role_keywords.json` | Title → role_category keyword mapping |
| `templates/live.html.j2` | Live web UI (FastAPI) — Jinja-less, pure JS SPA |
| `templates/daily_report.html.j2` | Static HTML report template |
| `tests/fixtures/` | Static ATS API response payloads for parser regression tests |
| `scripts/check_scrapers.py` | Scraper health check — runs all companies, caches results in `scraping_status.json` |
| `scripts/discover_workday_urls.py` | Auto-discovers correct Workday host/board for failing tenants |
| `scripts/scraping_status.json` | Cache of last check_scrapers run (gitignored) |

---

## ATS scraper coverage (98 active companies — 85 passing as of 2026-05-16)

| ATS | Count | Companies | Status |
|-----|-------|-----------|--------|
| Greenhouse | 39 | Anthropic, Stripe, Databricks, Figma, Scale AI, Cloudflare, Twilio, Datadog, Affirm, Brex, Chime, Gusto, Elastic, MongoDB, Grafana Labs, Netlify, Pagerduty, Hubspot, Intercom, Airtable, Amplitude, Mixpanel, LaunchDarkly, Vercel, Temporal, Pulumi, Cockroach Labs, CoreWeave, Airbnb, SAS Institute, Bandwidth, Lyft, Discord, Robinhood, Reddit, Duolingo, Asana, Pendo, Okta | ✅ All passing |
| Ashby | 13 | OpenAI, Notion, Plaid, Snowflake, Sentry, Cohere, PostHog, Zapier, Ramp, Linear, Supabase, Confluent, Benchling | ✅ All passing |
| Workday | 30 | Zendesk, Cisco, Capital One, Visa, Mastercard, Red Hat, Salesforce, Nvidia, Fidelity, Walmart, Morgan Stanley, BlackRock, Palo Alto Networks, Juniper Networks, CrowdStrike, Adobe, Workday + **13 failing** (see below) | ⚠️ 17 pass / 13 fail |
| Lever | 2 | Palantir, Wealthfront | ✅ All passing |
| Amazon | 1 | Amazon | ✅ Passing |
| Google | 1 | Google | ✅ Passing (Playwright) |
| Apple | 1 | Apple | ✅ Passing (curl_cffi) |
| Microsoft | 1 | Microsoft | ✅ Passing |
| Workable | 1 | Hugging Face | ✅ Passing |
| Rippling | 1 | Rippling | ✅ Passing |
| SmartRecruiters | 2 | ServiceNow, Arista Networks | ✅ All passing |
| Avature | 1 | Bloomberg | ✅ Passing (~300 jobs) |
| Oracle Cloud | 2 | JPMorgan Chase, American Express | ✅ All passing |
| SERP (ddgs) | 3 | Meta, Coinbase, Retool | ✅ All passing (10–20 jobs/company via DuckDuckGo) |

### Disabled companies (4)
| Company | Reason |
|---------|--------|
| Dell Technologies | Moved to Oracle Cloud HCM (internal); not worth separate scraper |
| MathWorks | Workday board requires SSO (401); no public board |
| Splunk | Acquired by and merged into Cisco; Cisco already scraped |
| HashiCorp | Acquired by IBM; IBM's Eightfold API not accessible (returns 404) |

### Failing companies — all Workday maintenance (13)
All return HTTP 422 `{"errorCode":"HTTP_422"}` from `myworkdayjobs.com`. This is a **global Workday maintenance event** as of 2026-05, not a config problem. All configs are correct.

| Company | Workday host |
|---------|-------------|
| Cohesity | cohesity.wd1.myworkdayjobs.com/External |
| Snyk | snyk.wd1.myworkdayjobs.com |
| Oracle | oracle.wd1.myworkdayjobs.com |
| Goldman Sachs | goldmansachs.wd1.myworkdayjobs.com |
| Qualcomm | qualcomm.wd5.myworkdayjobs.com |
| Akamai | akamai.wd1.myworkdayjobs.com |
| BNY Mellon | bnymellon.wd1.myworkdayjobs.com/BNYMellonCareers |
| Veeva Systems | veeva.wd1.myworkdayjobs.com |
| Uber | uber.wd5.myworkdayjobs.com |
| Lenovo | lenovoglobal.wd3.myworkdayjobs.com |
| Fortinet | fortinet.wd1.myworkdayjobs.com |
| Intuit | intuit.wd1.myworkdayjobs.com |
| NetApp | netapp.wd1.myworkdayjobs.com |

**Phase 4 plan:** Run `python scripts/check_scrapers.py --fresh` periodically. When the 422s resolve, these will auto-recover. If they don't recover within a few weeks, investigate FlareSolverr proxy as fallback.

---

## Scraping architecture

```
Greenhouse API (39) ────────────┐
Ashby API (13) ─────────────────┤
Lever API (2) ──────────────────┤
Workday POST API (30) ──────────┤
Amazon Jobs API (1) ────────────┤
Google Careers / Playwright (1) ┤
Apple Jobs / curl_cffi (1) ─────┼─► pipeline.py ──► SQLite (jobs.db) ──► ranker.py ──► shortlist ──► HTML report
Microsoft Careers API (1) ──────┤         │                                                               │
Workable API (1) ───────────────┤         └──────────────────────────────────────────────────────► FastAPI live UI
Rippling Jobs (1) ──────────────┤                                                                  localhost:8080
SmartRecruiters API (2) ────────┤
Avature REST (1) ───────────────┤
Oracle Cloud finder API (2) ────┤
DuckDuckGo SERP / ddgs (3) ─────┘
```

### Key design decisions
- **curl_cffi with `impersonate="chrome"`** — used by Workday, Apple, SERP, and Greenhouse (403 fallback) to bypass TLS fingerprinting bot checks
- **ddgs package** for SERP fallback — hits DDG's backend API (no HTML parsing, no CAPTCHA). Each company runs `DDGS().text(serp_query, max_results=20)` in a thread pool via `asyncio.to_thread`
- **Workday description enrichment** — descriptions are NOT in the job list API response; fetched separately per-job. Async, `Semaphore(5)`, cap 100 jobs/run
- **Rate limits** — Workday: 1 req/3s, LinkedIn: 1 req/5s, SERP: 1 req/10s, Amazon/Google/Apple: 1 req/2s
- **`insert_jobs()` returns `(count, inserted_ids)`** — pipeline uses IDs to trigger Workday description enrichment only for newly inserted jobs

### SERP fallback companies and why
| Company | Why not direct API |
|---------|-------------------|
| Meta | metacareers.com uses authenticated GraphQL — no public endpoint |
| Coinbase | Greenhouse board at coinbase.greenhouse.io requires Okta SSO |
| Retool | Gem ATS GraphQL at www.gem.com/graphql requires auth (403) |

### Oracle Cloud scraper details (`src/scrapers/oracle_cloud.py`)
- GET `https://{orc_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions`
- Finder: `findReqs;siteNumber={site},facetsList=...,limit=25,offset={N},sortBy=POSTING_DATES_DESC`
- Response: `items[0].TotalJobsCount`, `items[0].requisitionList[]`
- Job URL: `{orc_careers_url}/en/sites/{site}/job/{Id}`
- Companies: JPMC (`jpmc.fa.oraclecloud.com`, site `CX_1001`) and AmEx (`egug.fa.us2.oraclecloud.com`, site `CX_1`)

### Avature scraper details (`src/scrapers/avature.py`)
- Bloomberg only. Paginated REST: `GET https://careers.bloomberg.com/api/jobs`
- Returns up to 300 jobs (60s timeout — their server is slow but reliable)

---

## Scoring system

```
total_score = skill×35 + role×25 + visa×20 + recency×10 + company×10
```

| Factor | Weight | Logic |
|--------|--------|-------|
| Skill match | 35 | Keyword match of job description vs candidate skills. ~40% match = full score. |
| Role priority | 25 | Backend=1.0, Cloud=0.9, Fullstack=0.85, Frontend=0.75 … |
| Visa signal | 20 | Confirmed=1.0, Unknown=0.4, No sponsor=0.0 (hard disqualify from top 50) |
| Recency | 10 | Same-day=1.0, 1 day=0.9, 1 week=0.6, 2 weeks=0.35 |
| Company tier | 10 | Tier 1=1.0 (+fintech bonus 0.10), Tier 2=0.65, Tier 3=0.35 |

Senior role detection: if title or description implies 3+ years experience and no early-career signal, multiply `total_score × 0.35`.

---

## Live web UI features (`templates/live.html.j2`)

- Sidebar with companies grouped by industry (Tech / Fintech / Enterprise)
- Filter buttons: US Only, New Grad, sort by Score / Newest / Company
- Job cards with: score breakdown, experience badge, H1-B petition count, matched/missing skills
- `POST /api/refresh` triggers a full pipeline run from the browser
- API endpoints: `GET /api/jobs`, `GET /api/companies`, `GET /api/status`

---

## H1-B sponsorship data

`data/h1b_sponsors.json` contains pre-populated USCIS petition counts (FY2022–2024) for 54 companies.
The `companies` table has `h1b_petitions_recent` column populated at pipeline start from this file.
Run `myjobs update-h1b` to re-sync without doing a full scrape.

---

## Database schema notes

- `jobs.visa_signal`: 1=confirmed sponsor, 0=unknown, -1=will not sponsor
- `jobs.early_career`: 1 if entry-level/new-grad signals detected
- `jobs.exp_years_max`: max years of experience required (parsed from description)
- `companies.h1b_petitions_recent`: total H1-B petitions FY2022–2024
- `insert_jobs()` returns `(count: int, inserted_ids: list[int])` — pipeline uses IDs to enrich Workday descriptions

---

## Database inspection

```bash
sqlite3 jobs.db ".tables"
sqlite3 jobs.db "SELECT * FROM daily_runs ORDER BY run_date DESC LIMIT 5;"
sqlite3 jobs.db "SELECT c.name, COUNT(*) FROM jobs j JOIN companies c ON j.company_id=c.id GROUP BY c.name ORDER BY COUNT(*) DESC LIMIT 20;"
sqlite3 jobs.db "SELECT company_name, title, total_score, visa_signal FROM jobs j JOIN companies c ON j.company_id=c.id WHERE status='shortlisted' ORDER BY total_score DESC LIMIT 20;"
```

---

## Phase 2 — Resume generation (not yet built)

Requires `ANTHROPIC_API_KEY` in `.env`. Copy `.env.example` to `.env` and fill in the key.
Run `myjobs verify-api` to test the key.

Plan: use Claude API with prompt caching — base resume content as cached system prompt prefix, job description as per-job user message. Batch 50 jobs with `asyncio.Semaphore(3)`. Output JSON → HTML files alongside the report.

---

## Gitignored files

- `jobs.db` — SQLite database
- `.env` — API keys
- `output/*/` — daily reports (the `.gitkeep` in `output/` is tracked)
- `scripts/scraping_status.json` — check_scrapers cache

---

## Phase 0 — Operational safety (complete)

- **`src/utils/retry.py`** — `async_retry()`: exponential backoff with jitter, `Retry-After` header support. Integrated into `BaseScraper._request`.
- **`src/logger.py`** — JSON structured logging to stderr. `LOG_LEVEL` env var controls verbosity.
- **`tests/fixtures/`** — Static ATS API response payloads for parser regression tests.
- **`tests/test_parsers.py`** — 30 parser stability tests (5 × 6 ATS types). Run `pytest tests/test_parsers.py`.

---

## Adding a new ATS scraper

1. Create `src/scrapers/myats.py` inheriting `BaseScraper`
2. Implement `async def fetch_jobs(self, company, company_id) -> list[dict]`
3. Wire into `src/pipeline.py` alongside the other ATS blocks
4. Add `"ats_type": "myats"` entries to `data/companies.json`
5. If the ATS needs post-scrape description enrichment, follow the Workday pattern (`fetch_workday_description` + `_enrich_workday_descriptions` in pipeline)
6. Add a fixture in `tests/fixtures/` and a test class in `tests/test_parsers.py`
