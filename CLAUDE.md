# myjobs — Job Application Automation System

## What this project does

Daily pipeline that:
1. Scrapes job listings from Greenhouse and Lever APIs (~45 target companies)
2. Parses visa signals, role category, and experience requirements from each job
3. Scores every job on 5 factors (skill match, role priority, visa, recency, company tier)
4. Shortlists the top 50 and renders a ranked HTML report

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

# Full daily run: scrape + rank + HTML report
python -m src.cli run

# Or using the installed entry point
myjobs run

# Show top 20 jobs in terminal
myjobs show --top 20

# Show only backend roles
myjobs show --role backend

# Open today's HTML report in browser
myjobs open-report

# Mark a job as applied
myjobs apply <job_id>

# Application history
myjobs history --days 30

# Stats
myjobs stats

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
| `src/pipeline.py` | Orchestrates the full daily run |
| `src/scrapers/greenhouse.py` | Greenhouse public JSON API client |
| `src/scrapers/lever.py` | Lever public JSON API client |
| `src/renderer.py` | Jinja2 → HTML report |
| `src/database.py` | SQLite schema + all query helpers |
| `src/cli.py` | Typer CLI (all user-facing commands) |
| `data/companies.json` | Target companies list (edit to add/remove) |
| `data/visa_keywords.json` | Visa positive/negative signal phrases |
| `data/role_keywords.json` | Title → role_category keyword mapping |
| `templates/daily_report.html.j2` | HTML report template |

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
Greenhouse API ──┐
                 ├─► Scraper Layer ──► SQLite DB ──► Ranker ──► Shortlist ──► HTML Report
Lever API ───────┘
```

- No external server needed — SQLite file (`jobs.db`)
- All output in `output/YYYY-MM-DD/report.html`
- Rate-limited to 1 req/2s per company (async, up to 5 concurrent companies)

---

## Database inspection

```bash
sqlite3 jobs.db ".tables"
sqlite3 jobs.db "SELECT * FROM daily_runs ORDER BY run_date DESC LIMIT 5;"
sqlite3 jobs.db "SELECT company_name, title, total_score, visa_signal FROM jobs j JOIN companies c ON j.company_id=c.id WHERE status='shortlisted' ORDER BY total_score DESC LIMIT 20;"
```

---

## Phase 2 — Resume generation (not yet built)

Requires `ANTHROPIC_API_KEY` in `.env`. Copy `.env.example` to `.env` and fill in the key.

Plan: use Claude API with prompt caching — base resume content as cached system prompt prefix, job description as per-job user message. Batch 50 jobs with `asyncio.Semaphore(3)`. Output JSON → HTML files alongside the report.

---

## Gitignored files

- `jobs.db` — SQLite database
- `.env` — API keys
- `output/*/` — daily reports (the `.gitkeep` in `output/` is tracked)

---

## Adding a new ATS scraper (Phase 3)

1. Create `src/scrapers/myats.py` inheriting `BaseScraper`
2. Implement `async def fetch_jobs(self, company, company_id) -> list[dict]`
3. Add scraper invocation to `src/pipeline.py` alongside Greenhouse/Lever blocks
4. Add `"ats_type": "myats"` entries to `data/companies.json`
