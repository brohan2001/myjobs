# Repo map

Short reference so later phases don't need to re-read the repo. Keep it current when modules move.
Last verified: 2026-10-11 (Phase 0).

## Entry points
| Command | Code | What it does |
|---|---|---|
| `myjobs run` | `src/cli.py:111` | CSV sync → crawl queues drained (HTTP workers only) → `run_scoring` → HTML report → `daily_runs` row |
| `myjobs serve` | `src/cli.py:377` → `src/server.py` | FastAPI on 127.0.0.1:8080, reads Postgres |
| `myjobs generate` | `src/ai/generator.py` | Claude resume bullets + cover letter for top jobs |
| `myjobs show/apply/history/stats/company/update-h1b/verify-api` | `src/cli.py` | Small CLI utilities |
| `crawler run / run-browser / sync / prune-scrape-queues` | `src/cli.py:641-690` | Queue workers and sync. `crawler board` is broken |
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
| `src/ranker.py`, `src/scoring_config.py` | 5-factor score and shortlist (US/visa-biased) | myjobs |
| `src/server.py`, `templates/live.html.j2` | Live web UI and JSON API | myjobs |
| `src/renderer.py`, `templates/daily_report.html.j2` | Static daily HTML report | myjobs |
| `src/ai/generator.py` | Claude generation; profile from `PROFILE_PATH` | myjobs |
| `src/metrics.py` | Prometheus stubs | myjobs |
| `src/logger.py` | `get_logger(__name__)` | myjobs |

## Data
- `data/companies.csv`: `slug,name,website,industry,tier,enabled,h1b_petitions_recent` (2,882 rows)
- `data/boards.csv`: `company_slug,board_slug,board_url,monitor_type,monitor_config,scraper_type,scraper_config` (3,169 rows)
- `data/{occupations,occupation_domains,seniority,technologies}.csv`: taxonomy (migration 0007)
- `data/{role_keywords,visa_keywords,h1b_sponsors}.json`: scoring inputs (visa and H1B files are due for deletion in Phase 2A)
- `private/` (gitignored): real profile, resumes, PII patterns, target company notes

## Tests
- `tests/test_ranker.py`, `tests/test_renderer.py`: pure functions (85 tests)
- `tests/characterization/`: no-network characterization tests for monitors and scrapers (Phase 0)
- `tests/fixtures/`: legacy fixtures (partly re-used by characterization)

## Docs
`docs/AUDIT.md`, `docs/SCRAPING_REPORT.md`, `docs/REVAMP_PLAN.md`, `docs/DECISIONS.md`, `docs/baseline/`, `delegation/`.
