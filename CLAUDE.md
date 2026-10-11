# myjobs: public feed of the latest jobs (revamp in progress)

Continuous crawler over ~3,169 company career boards (2,882 companies) → Postgres → public read-only API and web feed (jseek.co-style).
**Revamp underway**: worldwide coverage, strongest for India. Per-user profiles come later (DECISIONS D10). Read `docs/REVAMP_PLAN.md`, `docs/DECISIONS.md`
and `docs/REPO_MAP.md` before starting work. `docs/AUDIT.md` and `docs/SCRAPING_REPORT.md` describe the current state.

---

## Hard rules
- **Public repo: no personal data in tracked files.** Real profile, resumes and notes live in `private/` (gitignored). The local
  pre-commit hook (gitleaks + `private/pii_patterns.txt`) blocks leaks. Don't bypass it.
- **Never fabricate resume content.** Tailoring may select and reorder real content only.
- **Branches:** work on `revamp/<phase>` branches, small logical commits, never commit to `main`. The auto-push hook is disabled.
- **Respect the web:** prefer public ATS APIs; no scrapers for Naukri/LinkedIn or other ToS-forbidden portals.
- **Scraper changes** must keep `tests/characterization/` green or update snapshots deliberately (see DECISIONS D5).
- `src/core/` and `src/shared/` are a fork of colophon-group/jobseek (MIT, see `THIRD_PARTY_NOTICES.md`). We may edit them.

---

## Running

```bash
pip install -e ".[dev]"
python -m playwright install chromium     # for render/browser boards
docker compose up -d                       # Postgres 16 + Redis 7 (REDIS_PORT/POSTGRES_PORT override host ports)
alembic upgrade head                       # migrations in src/migrations/versions/
python scripts/load_geonames.py            # location taxonomy (once; idempotent)
python scripts/populate_taxonomy.py        # seniority/occupation taxonomy (once)

myjobs worker             # crawl continuously (syncs CSV config first); Ctrl-C to stop
myjobs worker --no-browser
myjobs crawl              # one pass: drain ready queues, then exit
myjobs serve              # API + interim page at http://127.0.0.1:8080 (docs at /api/docs)
myjobs stats              # freshness + coverage
myjobs sync               # CSV → Postgres + Redis queues
myjobs company list|add|disable

python scripts/baseline_snapshot.py        # coverage snapshot → docs/baseline/
python scripts/discover_companies.py data/candidates/india_companies.csv [--apply]   # candidate → verified board
python scripts/discover_companies.py <gone.csv> --rediscover --apply                 # re-find boards that went away

cd web && npm install && API_ORIGIN=http://127.0.0.1:8080 npm run dev               # Next.js feed (direction C)
```

Env: copy `.env.example` → `.env` (`LOCAL_DATABASE_URL`, `REDIS_URL`, `API_RATE_LIMIT_PER_MINUTE`, `API_CORS_ORIGINS`, optional proxy settings).

---

## Architecture (short; full map in docs/REPO_MAP.md)

```
data/companies.csv + data/boards.csv → src/sync.py → Postgres (company, job_board) + Redis queues
src/workers/pipeline.py → src/core/monitors/* (37 types) → src/core/scrapers/* (16 types) → job_posting + descriptions
src/processing/cpu.py enrichment (GeoNames locations, salary, seniority, occupation)
src/api/ (FastAPI): /api/v1/jobs|jobs/{id}|companies|locations|stats|coverage (+ interim page in src/api/static/)
web/ (Next.js App Router + TS): server-rendered feed, job detail, coverage; talks to the API via /api rewrite
src/discovery/ + scripts/discover_companies.py: candidate companies → careers board → ATS → robots/parse checks → registry or review queue
```

- Config: `src/config.py` (pydantic-settings).
- DB: Postgres via asyncpg (`src/db.py`); schema in alembic migrations 0001–0009.
- Queue: `src/redis_queue.py` + `src/lua/*.lua` (per-key rate limit, leases, reaper, dead letter).
- SSRF guard: `src/shared/ssrf.py`, installed by `create_http_client` (used by the worker and discovery).
- robots.txt: `src/shared/robots.py`. Site-reading monitors honour it; ATS API monitors (`API_MONITORS`) are exempt.
- Delegation: agy for ~50% of the work (Gemini 3.8 Flash first). Briefs live in `delegation/`; verify with tests, not by reading code.

---

## Testing

```bash
python3 -m pytest -q                        # all tests, no network
python3 -m pytest tests/characterization    # monitor/scraper behavior pins
python3 -m pytest tests/api                 # public API (fake pool, no DB)
```

`asyncio_mode="auto"`, so no `@pytest.mark.asyncio` needed.

---

## Code style
- Logging: `get_logger(__name__)` from `src/logger.py`; never `print()`.
- Record non-obvious choices in `docs/DECISIONS.md`.
- Delegated tasks get briefs in `delegation/<phase>-<NN>-<slug>.md` (see `delegation/TEMPLATE.md`).

## Gitignored
`.env`, `private/`, `jobs.db*`, `output/`, `scripts/scraping_status.json`, `.claude/`, `.history/`
