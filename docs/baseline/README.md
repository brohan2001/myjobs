# Baseline snapshots

Read-only snapshots of crawl health, produced by `scripts/baseline_snapshot.py`.

- `YYYY-MM-DD.{json,md}`: live Postgres snapshot (`source=postgres`).
- `YYYY-MM-DD-legacy.{json,md}`: snapshot of the old SQLite `jobs.db` (`source=legacy_sqlite`).

```bash
python3 scripts/baseline_snapshot.py                       # Postgres, DSN from settings.local_database_url
python3 scripts/baseline_snapshot.py --dsn postgresql://...
python3 scripts/baseline_snapshot.py --legacy-sqlite /path/to/jobs.db
```

Contents: companies (total / with active postings), boards per crawler type
(total, enabled, failing, disabled, failure %), active postings per crawler
type, top 50 companies, boards with a success in the last 48 h, and the latest
5 `daily_runs`.

Caveats

- Legacy mode has no `is_active` flag, so every row in `jobs` counts as an
  active posting, and "crawler type" is `boards.monitor_type` for boards and
  `jobs.ats_type` for postings.
- Legacy "last 48 h" is measured against the time the snapshot was generated,
  so it is 0 for a stale `jobs.db`.
- `tz_suspect=true` on a run means the duration was negative or only one of
  the two timestamps carried a timezone. The value is reported as stored, not
  corrected. In the 2026-05-20 legacy snapshot, 3 of the 5 runs are flagged
  (`started_at` looks like UTC from `datetime('now')`, `finished_at` looks
  like local time).
