# Repo map

Short reference so later phases don't need to re-read the repo. Keep it current when modules move.
Last verified: 2026-10-11 (Phase 1 feed).

## Entry points
| Command | Code | What it does |
|---|---|---|
| `myjobs worker` | `src/cli.py` `_run_worker` | Sync, then run the HTTP (+ browser) pipelines until SIGTERM |
| `myjobs crawl` | `src/cli.py` `_drain_once` | Drain ready queues once |
| `myjobs serve` | `src/api/app.py` | Public FastAPI feed on 127.0.0.1:8080 |
| `myjobs stats / sync / company …` | `src/cli.py` | Utilities |
| `scripts/load_geonames.py`, `scripts/populate_taxonomy.py` | | One-time reference data loads |
| `python -m src.workspace` (`ws`) | `src/workspace/` | Agent-driven board config workspace from jobseek (discovery, probing). Not installed as a script |

Infra: `docker-compose.yml` provides Postgres 16 and Redis 7. Migrations: `alembic upgrade head` (`src/migrations/`).

## Modules
| Path | Role | Origin |
|---|---|---|
| `src/config.py` | pydantic-settings: DSN, Redis, proxy, SSRF allowlist, concurrency | myjobs |
| `src/db.py` | asyncpg pool | myjobs |
| `src/sync.py` | `data/companies.csv` + `data/boards.csv` → `company` / `job_board` + Redis enqueue | myjobs (jobseek-shaped) |
| `src/redis_queue.py`, `src/lua/*.lua` | Priority queues, per-key rate limit, lease/heartbeat/reaper/dead letter | jobseek |
| `src/workers/pipeline.py` | Worker loop: claim → monitor → scrape → persist | jobseek, adapted |
| `src/processing/board.py` | Monitor one board, diff postings, strikes/disable, delist logic | jobseek |
| `src/processing/scrape.py` | Scrape one URL-only posting, store description | jobseek |
| `src/processing/cpu.py` | Enrichment: location/salary/seniority/occupation/technology resolve | jobseek, adapted |
| `src/processing/r2_stage.py` | Content hashing (R2 upload unused) | jobseek |
| `src/queries/*.py` | SQL for monitor/scrape/lookups | jobseek, adapted |
| `src/core/monitors/` | 37 monitor types (see SCRAPING_REPORT §2) | jobseek |
| `src/core/scrapers/` | 16 scraper types | jobseek |
| `src/core/*_resolve.py`, `salary_extract.py`, `experience_extract.py` | Enrichment extractors | jobseek |
| `src/shared/http.py`, `http_retry.py` | httpx client factory (SSRF transport, UA), retry helper | jobseek |
| `src/shared/ssrf.py` | SSRF guard (resolved-IP check per hop) | jobseek |
| `src/shared/browser.py`, `api_sniff.py` | Playwright and XHR sniffing | jobseek |
| `src/shared/tdm.py` | W3C TDM-reservation opt-out | jobseek |
| `src/api/app.py` | FastAPI app: routes, serialization, nh3 sanitizing, rate-limit middleware, security headers | myjobs |
| `src/api/queries.py` | Feed SQL (pure `build_jobs_query`, keyset cursors) | myjobs |
| `src/api/locations.py` | In-memory GeoNames index (country/macro → descendant ids, labels, search) | myjobs |
| `src/api/ratelimit.py` | Per-IP fixed-window limiter (Redis or local) | myjobs |
| `src/api/static/` | Interim feed page (replaced in Phase 3) | myjobs |
| `src/metrics.py` | Prometheus stubs | myjobs |
| `src/logger.py` | `get_logger(__name__)` | myjobs |

## Data
- `data/companies.csv`: `slug,name,website,industry,tier,enabled` (2,882 rows)
- `data/boards.csv`: `company_slug,board_slug,board_url,monitor_type,monitor_config,scraper_type,scraper_config` (3,169 rows)
- `data/{occupations,occupation_domains,seniority,technologies}.csv`: taxonomy (migration 0007)
- `private/` (gitignored): real profile, resumes, PII patterns, target company notes

## Tests
- `tests/characterization/`: no-network characterization tests for monitors, scrapers, retry, registry, baseline script
- `tests/api/`: public API tests against a fake pool
- `tests/test_load_geonames.py`: GeoNames parsing + resolver integration

## Docs
`docs/AUDIT.md`, `docs/SCRAPING_REPORT.md`, `docs/REVAMP_PLAN.md`, `docs/DECISIONS.md`, `docs/baseline/`, `delegation/`.
