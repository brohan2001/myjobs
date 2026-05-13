# myjobs — Job Application Automation System

## What this project does

Daily pipeline that:
1. Scrapes job listings from 102 target companies across 7 ATS types
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
```

---

## Key files

| File | Purpose |
|------|---------|
| `src/config.py` | Skill groups, role weights, score weights — edit here to tune ranking |
| `src/ranker.py` | All 5 scoring functions + signal parsing |
| `src/pipeline.py` | Orchestrates the full daily run (scrape → enrich → parse → rank → shortlist → render) |
| `src/scrapers/greenhouse.py` | Greenhouse public JSON API client |
| `src/scrapers/lever.py` | Lever public JSON API client (paginated, cap 500) |
| `src/scrapers/workday.py` | Workday POST pagination API; descriptions fetched separately by pipeline |
| `src/scrapers/amazon.py` | Amazon Jobs search JSON API |
| `src/scrapers/google.py` | Google Careers public API (`careers.google.com/api/v3/search`) |
| `src/scrapers/apple.py` | Apple Jobs public API (`jobs.apple.com/api/role/search`) |
| `src/scrapers/linkedin.py` | LinkedIn per-company (blocked by login wall) + broad keyword search |
| `src/server.py` | FastAPI live web UI (`myjobs serve`) |
| `src/renderer.py` | Jinja2 → HTML daily report |
| `src/database.py` | SQLite schema + all query helpers; H1-B data; US location detection |
| `src/cli.py` | Typer CLI (all user-facing commands) |
| `data/companies.json` | 102 target companies with ATS config (edit to add/remove) |
| `data/h1b_sponsors.json` | USCIS H1-B petition counts for 54 companies (FY2022–2024) |
| `data/visa_keywords.json` | Visa positive/negative signal phrases |
| `data/role_keywords.json` | Title → role_category keyword mapping |
| `templates/live.html.j2` | Live web UI (FastAPI) — Jinja-less, pure JS SPA |
| `templates/daily_report.html.j2` | Static HTML report template |

---

## ATS scraper coverage (102 companies total)

| ATS | Count | Key companies | Notes |
|-----|-------|---------------|-------|
| Greenhouse | 55 | Anthropic, OpenAI, Stripe, Databricks, Airbnb, Lyft, Reddit, Discord… | Fully working |
| Workday | 35 | Microsoft, Cisco, Oracle, Goldman Sachs, Nvidia, Salesforce, Uber, JPMorgan, Capital One… | Working; descriptions enriched async post-scrape |
| Lever | 6 | Ramp, Vercel, Temporal, Linear, Pulumi, Wealthfront | Fully working, paginated |
| Amazon | 1 | Amazon | Working (custom JSON API) |
| Google | 1 | Google | Working (public careers API, full descriptions) |
| Apple | 1 | Apple | Working (public jobs API) |
| LinkedIn | 3 | Meta, Arista Networks, Juniper Networks | Mostly blocked by LinkedIn login wall; broad keyword search also runs |

**Note on Meta:** `metacareers.com` uses an authenticated GraphQL API — no clean scraping option. Kept on LinkedIn (returns 0 most of the time). Revisit if a public endpoint appears.

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

## Architecture

```
Greenhouse API ─────┐
Lever API ──────────┤
Workday API ────────┤
Amazon Jobs API ────┼─► Scraper Layer ──► SQLite DB ──► Ranker ──► Shortlist ──► HTML Report
Google Careers API ─┤                         │                                      │
Apple Jobs API ─────┤                         └──────────────────────────────► FastAPI Live UI
LinkedIn (limited) ─┘
```

- No external server needed for reports — SQLite file (`jobs.db`)
- All static output in `output/YYYY-MM-DD/report.html`
- Live UI: `myjobs serve` starts FastAPI on `http://localhost:8080`
- Rate-limited per ATS (Workday: 1 req/3s, LinkedIn: 1 req/5s, Amazon/Google/Apple: 1 req/2s)
- Workday description enrichment: async, `Semaphore(5)`, cap 100 jobs/run

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

---

## Adding a new ATS scraper

1. Create `src/scrapers/myats.py` inheriting `BaseScraper`
2. Implement `async def fetch_jobs(self, company, company_id) -> list[dict]`
3. Wire into `src/pipeline.py` alongside the other ATS blocks
4. Add `"ats_type": "myats"` entries to `data/companies.json`
5. If the ATS needs post-scrape description enrichment, follow the Workday pattern (`fetch_workday_description` + `_enrich_workday_descriptions` in pipeline)
