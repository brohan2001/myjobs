# myjobs

A public, continuously updated feed of tech jobs, read straight from company career pages. It covers the world and is
strongest for India. The registry holds about 6,000 companies and 7,800 boards on 100+ ATS types (Greenhouse, Ashby, Lever,
Workday…). There's no sign-up: a web feed and a read-only JSON API.

## How it works

```
data/{companies,boards}.csv ─► sync ─► Redis queues ─► worker: monitors find postings, scrapers fetch them ─► Postgres ─► API ─► web
```

- **Politeness:** per-domain rate limits in Redis; robots.txt for site-reading monitors; an honest User-Agent (D14).
- **SSRF guard** on every request and redirect (`src/shared/ssrf.py`).
- **Enrichment:** GeoNames locations (D13), salaries including INR/LPA, seniority, occupation and years of experience.
- **Tech only** (D27): non-tech postings are dropped before they're stored.

## Repo map

| Path | What |
|---|---|
| `data/` | Company and board registry, plus taxonomy CSVs |
| `src/sync.py` | CSV → Postgres + Redis queues |
| `src/workers/pipeline.py` | The crawl loop |
| `src/core/monitors/`, `src/core/scrapers/` | Per-ATS code, vendored from jobseek (`docs/UPSTREAM.md`) |
| `src/core/*_resolve.py`, `*_extract.py`, `tech_gate.py` | Enrichment and the tech filter (ours) |
| `src/processing/`, `src/queries/`, `src/lua/`, `src/redis_queue.py` | Pipeline stages, SQL, queue scripts |
| `src/api/` | FastAPI: `/api/v1/jobs`, `jobs/{id}`, `companies`, `locations`, `stats`, `coverage` |
| `src/cli.py` | `myjobs` commands: worker, crawl, serve, sync, stats, health, boards, company |
| `src/migrations/` | Alembic schema |
| `web/` | Next.js feed: list, job detail, coverage |
| `scripts/` | `dev.sh`, taxonomy loaders, jseek parity check, upstream registry import |
| `deploy/laptop/` | Production setup on the home laptop |

## Run it locally

```bash
cp .env.example .env
pip install -e ".[dev]" && python -m playwright install chromium
./scripts/dev.sh        # Postgres + Redis + migrations + worker + API :8090 + web :3000 (--no-worker, --no-browser)
```

On a new database, first run `python scripts/load_geonames.py && python scripts/populate_taxonomy.py`.
Tests: `python3 -m pytest -q` (no network).

## Production

It runs on the user's home laptop: `docs/DEPLOY.md`.

## Docs

- `docs/DECISIONS.md`: why things are the way they are.
- `docs/DEPLOY.md`: the laptop setup.
- `docs/UPSTREAM.md`: how to re-sync the vendored jobseek code.

## Credits

The crawler core, queue design and registry data come from [colophon-group/jobseek](https://github.com/colophon-group/jobseek)
(MIT), and locations from [GeoNames](https://www.geonames.org/) (CC BY 4.0). See `THIRD_PARTY_NOTICES.md`. The project's own
licence hasn't been chosen yet.
