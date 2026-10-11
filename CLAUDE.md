# myjobs: job discovery portal (revamp in progress)

Daily pipeline: ~3,169 boards (2,882 companies) → monitor → scrape → enrich → score → feed/report.
**Revamp underway**: becoming a multi-user portal that covers the world and is strongest for India. Read `docs/REVAMP_PLAN.md`, `docs/DECISIONS.md`
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
pip install -e .
python -m playwright install chromium     # for render/browser boards
docker compose up -d                       # Postgres 16 + Redis 7
alembic upgrade head                       # migrations in src/migrations/versions/

myjobs run                # sync CSVs → crawl (HTTP workers) → score → HTML report
myjobs serve              # FastAPI live UI at http://127.0.0.1:8080
myjobs show --top 20
myjobs generate --top 10  # Claude tailoring; profile from PROFILE_PATH (default private/profile.txt)
myjobs company list|add|disable

crawler sync              # CSV → Postgres + Redis queues
crawler run               # drain HTTP queues
crawler run-browser       # drain browser queues (not run by `myjobs run`)

python scripts/baseline_snapshot.py        # coverage snapshot → docs/baseline/
```

Env: copy `.env.example` → `.env` (`LOCAL_DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`, optional proxy settings).

---

## Architecture (short; full map in docs/REPO_MAP.md)

```
data/companies.csv + data/boards.csv → src/sync.py → Postgres (company, job_board) + Redis queues
src/workers/pipeline.py → src/core/monitors/* (37 types) → src/core/scrapers/* (16 types) → job_posting + descriptions
src/processing/cpu.py enrichment → src/ranker.py scoring → src/renderer.py / src/server.py
```

- Config: `src/config.py` (pydantic-settings). Scoring constants: `src/scoring_config.py`.
- DB: Postgres via asyncpg (`src/db.py`); schema in alembic migrations 0001–0008.
- Queue: `src/redis_queue.py` + `src/lua/*.lua` (per-key rate limit, leases, reaper, dead letter).
- SSRF guard: `src/shared/ssrf.py`. Note: `myjobs run` currently bypasses it (AUDIT §8, bug 1).

---

## Testing

```bash
python3 -m pytest -q                        # all tests, no network
python3 -m pytest tests/characterization    # monitor/scraper behavior pins
```

`asyncio_mode="auto"`, so no `@pytest.mark.asyncio` needed.

---

## Code style
- Logging: `get_logger(__name__)` from `src/logger.py`; never `print()`.
- Record non-obvious choices in `docs/DECISIONS.md`.
- Delegated tasks get briefs in `delegation/<phase>-<NN>-<slug>.md` (see `delegation/TEMPLATE.md`).

## Gitignored
`.env`, `private/`, `jobs.db*`, `output/*/`, `scripts/scraping_status.json`, `.claude/`, `.history/`
