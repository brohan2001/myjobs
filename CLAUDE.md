# myjobs: public feed of the latest tech jobs

A continuous crawler over ~7,800 company career boards (~6,000 companies) → Postgres → a read-only API and a Next.js feed
(jseek.co-style). Worldwide, strongest for India, tech jobs only (D27), at least jseek.co's coverage (D28). Per-user features
come later (D10). It runs on the user's home laptop (D29).

Read `README.md` (repo map), `docs/DECISIONS.md` and, for production, `docs/DEPLOY.md` before starting work.

## Hard rules
- **Public repo: no personal data in tracked files.** Profiles, resumes and notes live in `private/` (gitignored). The
  pre-commit hook (gitleaks + `private/pii_patterns.txt`) blocks leaks; don't bypass it.
- **Never fabricate resume content.** Tailoring may only select and reorder real content.
- **Branches:** work on `revamp/<phase>` branches in small logical commits; never commit to `main`.
- **Respect the web:** prefer public ATS APIs and honour robots.txt for site-reading monitors. The portal monitors are allowed
  (D25); ask before adding a new portal (e.g. Naukri).
- **Scraper changes** keep `tests/characterization/` green, or update the snapshots deliberately (D5).
- `src/core/` and `src/shared/` are vendored from jobseek (MIT). Edit them only through the deltas in `docs/UPSTREAM.md`.
- **No bloat:** keep the codebase short and readable. Cut code nothing uses, but list the removals and confirm them with the
  user first.

## Commands
```bash
./scripts/dev.sh             # local: DBs + migrations + worker + API :8090 + web :3000
myjobs worker | crawl | serve | sync | stats | health | boards <company|ats> | company add|list|disable
python3 -m pytest -q         # all tests, no network (asyncio_mode=auto)
python scripts/jseek_parity.py --api <url>   # coverage gaps against jseek.co
git push laptop <branch> && ssh rohan@192.168.29.132 '~/myjobs/deploy/laptop/setup.sh'   # deploy
```

## Code style
- Config in `src/config.py` (pydantic-settings, `.env`). Logging: `get_logger(__name__)` from `src/logger.py`; never `print()`.
- Schema changes go in a new alembic migration in `src/migrations/versions/`.
- Record non-obvious choices in `docs/DECISIONS.md`.
- Delegation to agy (D17): briefs go in `delegation/<phase>-<NN>-<slug>.md` (`delegation/TEMPLATE.md`); verify the work with tests.
