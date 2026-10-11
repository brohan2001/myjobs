# Decisions

Each entry records a non-obvious choice and its reason. Newest at the bottom. "User" means the user decided; "Default" means the orchestrator chose it and it can be overridden.

## D1: Postgres + Redis are the baseline (User, 2026-10-11)
The code had already been ported to Postgres + Redis + alembic. We keep that instead of the brief's "SQLite behind a repository"
assumption. Repository interfaces still wrap persistence (Phase 1.3). The legacy SQLite `jobs.db` is used only for the historical baseline.

## D2: Purge personal data from git history (User, 2026-10-11)
The repo is public and had resumes, email and visa status tracked since the first commit. We ran `git filter-repo` path removal plus string
replacement and force-pushed `main` once (the only time `main` is touched). A mirror backup is kept outside the repo. See AUDIT §10 for residual risk.

## D3: Auto-push Stop hook disabled during the revamp (User, 2026-10-11)
It ran `git add -A && commit && push` on any branch, which conflicts with per-phase branches and small commits. We removed it from
`.claude/settings.json` (local, gitignored). The script stays in `.claude/hooks/` for re-enabling later.

## D4: We own the jobseek fork (Default, 2026-10-11)
`src/core/` and `src/shared/` come from colophon-group/jobseek (MIT). The old "vendored, do not edit" rule is dropped: we will change monitors
(politeness, India ATS, bug fixes). Attribution is in `THIRD_PARTY_NOTICES.md`. Fork point: commits `fa17282` (Monitor→Scraper port) and `2dceb26` (Postgres + Redis port), post-rewrite SHAs. The upstream jobseek commit isn't recorded; Phase 2B should pin it by diffing against upstream.

## D5: Characterization tests before any scraper change (Default, 2026-10-11)
`tests/characterization/` pins current monitor and scraper outputs with no network. Changing a pinned output requires updating the
snapshot in the same commit with a reason in the message.

## D6: Politeness posture (Default, pending user answer to Q1)
Proposed: honest identifying UA, honor robots.txt for permission, honor `Retry-After`, stealth and proxy off by default. Boards that
become blocked are quarantined and reported rather than silently dropped.

## D7: No root LICENSE chosen yet (Default, 2026-10-11)
Choosing the project's own license is the user's call (open question). Only the third-party MIT notice was added.

## D8: Local pre-commit PII guard (Default, 2026-10-11)
`.git/hooks/pre-commit` runs gitleaks (`.gitleaks.toml`) and greps staged additions for patterns in `private/pii_patterns.txt`.
Patterns stay private so the guard itself doesn't leak the data. Not enforced in CI yet (Phase 4).

## D9: Phase 0 WIP committed as a snapshot, not fixed (Default, 2026-10-11)
The uncommitted server/UI work and migration 0008 were committed unchanged on `revamp/phase-0-audit`, so the baseline matches the code
that produced it. Its bugs are listed in AUDIT §4 and §8.
