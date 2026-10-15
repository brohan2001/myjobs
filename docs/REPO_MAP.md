# Repo map

Keep this current when modules move. Last verified: 2026-10-15.

## Entry points
| Command | Code | What it does |
|---|---|---|
| `myjobs worker` | `src/cli.py` `_run_worker` | Sync, then run the HTTP (+ browser) pipelines until SIGTERM |
| `myjobs crawl` | `src/cli.py` `_drain_once` | Drain ready queues once |
| `myjobs serve` | `src/api/app.py` | Public read-only API |
| `myjobs stats / health / sync / company …` | `src/cli.py`, `src/health.py` | Operator utilities |
| `scripts/dev.sh` | | Local start: DBs, migrations, worker, API, web |
| `scripts/discover_companies.py`, `scripts/triage_review.py` | `src/discovery/` | Candidate company → board, and the review queue |
| `scripts/load_geonames.py`, `scripts/populate_taxonomy.py` | | One-time reference data loads |

Infra: `docker-compose.yml` (Postgres 16, Redis 7). Migrations: `alembic upgrade head` (`src/migrations/`).

## Modules
| Path | Role | Origin |
|---|---|---|
| `src/config.py`, `src/db.py`, `src/logger.py` | Settings, asyncpg pool, logging | myjobs |
| `src/sync.py` | `data/*.csv` → `company` / `job_board` + Redis enqueue | myjobs |
| `src/redis_queue.py`, `src/lua/*.lua` | Domain queues, rate limits, leases, reaper, dead letter | jobseek |
| `src/workers/pipeline.py` | Worker loop: claim → monitor → scrape → persist | jobseek, adapted |
| `src/processing/board.py` | Monitor one board, diff postings, delist | jobseek |
| `src/processing/scrape.py`, `r2_stage.py` | Scrape a posting; description change detection and storage (the "r2" name is historical) | jobseek |
| `src/processing/cpu.py` | Enrichment: location, salary, seniority, occupation, technology | jobseek, adapted |
| `src/queries/*.py` | SQL for monitor/scrape/lookups | jobseek |
| `src/core/monitors/`, `src/core/scrapers/` | Board readers and job-page readers | jobseek |
| `src/core/static_registry.py` | Monitor/scraper classification without importing the core | jobseek |
| `src/core/*_resolve.py`, `*_extract.py`, `salary_inr.py`, `hashing.py` | Enrichment extractors | jobseek + myjobs |
| `src/shared/` | HTTP client (SSRF guard, UA), retries, browser, robots.txt, TDM | jobseek + myjobs |
| `src/metrics.py` | Prometheus counters (to be removed with the core re-sync, D26) | jobseek |
| `src/api/` | FastAPI app, feed SQL, GeoNames index, rate limiter | myjobs |
| `src/discovery/` | Candidate → careers page → ATS → validation → registry or review | myjobs (+ jobseek career-page finder) |
| `src/company_type.py`, `src/health.py` | Company-type taxonomy (D21), health alerts (D23) | myjobs |
| `web/` | Next.js feed | myjobs |

## Data
- `data/companies.csv`, `data/boards.csv`: the registry.
- `data/{occupations,occupation_domains,seniority,technologies}.csv`, `data/company_tags.csv`: taxonomies.
- `data/candidates/`: discovery inputs and review queues.
- `private/` (gitignored): personal data.

## Tests
- `tests/characterization/`: no-network monitor/scraper pins (D5).
- `tests/api/`: API against a fake pool. `tests/discovery/`: discovery pipeline.
- `tests/test_*.py`: robots, UA, salary, health, company type, GeoNames, triage.
- `web/src/lib/*.test.ts`: frontend (vitest).

## Docs
`REVAMP_PLAN.md` (status and next work), `DECISIONS.md`, `DEPLOY.md`, `HANDOFF.md`, `JSEEK_INTEGRATION.md`, `research/`.
