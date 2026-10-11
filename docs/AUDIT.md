# Audit (Phase 0, 2026-10-11)

Companion docs: `REPO_MAP.md` (module map), `SCRAPING_REPORT.md` (pipeline deep-dive and baseline), `REVAMP_PLAN.md`, `DECISIONS.md`.

## 1. The brief vs the code
| Brief said | Code says |
|---|---|
| Scraping design borrowed from JSeek (resume-extension) | Vendored from **colophon-group/jobseek** (MIT, third party). The user's JSeek extension is a content script that runs *on* jseek.co. Shared ideas with the extension: none in code |
| 30+ ATS integrations | True: 41 monitor types and 16 scrapers |
| Resumable staged caching | Redis leases, reaper and dead letter make runs resumable. "Staging" (`r2_stage.py`) only hashes; the R2 upload is dead code |
| TLS fingerprint spoofing | **Gone.** No curl_cffi after the port. Fake Chrome UA, an `ssl` tweak and Playwright stealth only |
| Per-host rate limits | Per *throttle key* (one per ATS for API boards, hostname otherwise) |
| SSRF guard with resolved-IP validation | True, per redirect hop. No IP pinning, and **bypassed by `myjobs run` for most boards** |
| Hand-rolled SQLite migrations | Replaced by **alembic on Postgres** (0001–0007, plus an untracked 0008 committed in Phase 0) |
| Claude API with prompt caching | True (`cache_control: ephemeral`, `claude-sonnet-4-6`). No router or fallback |
| Weighted 5-factor score, top 50 | True, plus a hidden 0.35× senior multiplier |
| Early server-side work | FastAPI with 5 endpoints, no auth. WIP partially done (§4) |
| SQLite (CLAUDE.md) | Postgres + Redis. CLAUDE.md was stale (fixed in Phase 0) |

## 2. Data flow (today)
```
data/companies.csv + boards.csv
   └─ src/sync.py ──► Postgres company, job_board ──► Redis monitor queues (3 priorities × http|browser)
src/workers/pipeline.py (claim via Lua, per-key rate limit, lease+heartbeat)
   ├─ monitor (src/core/monitors/*)  ── rich ──► job_posting rows
   └─ URL-only ──► scrape queue ──► src/core/scrapers/* ──► job_posting + descriptions
src/processing/cpu.py  enrichment: location ids, salary(+EUR), experience, seniority, occupation, technology
src/ranker.py run_scoring  ──► *_score, total_score, status='shortlisted' (top 50)
src/renderer.py ──► output/<date>/report.html      src/server.py ──► /api/jobs (live UI)
src/ai/generator.py ──► output/<date>/applications/*.md
```

## 3. Database schema (Postgres, alembic)
| Migration | Adds |
|---|---|
| 0001 | `job_board` (crawler_type, board_url unique, scheduling, failures, status, throttle_key, metadata JSONB, browser flags), `job_posting` (source_url unique, board_id, is_active, titles[], locales[], location_ids[]/types[], salary min/max/currency/period/eur, experience range, taxonomy ids, missing_count, enrichment JSONB), `descriptions`, `exporter_state` |
| 0002 | `company` (slug, name, website, logo, industry, extras…) |
| 0003 | `indexnow_submission` (unused here) |
| 0004 | Backfill: delist postings on disabled or gone boards |
| 0005 | Partial index `idx_jp_company_active` |
| 0006 | myjobs scoring columns on `job_posting` (`visa_signal`, `early_career`, `role_category`, `*_score`, `total_score`, `status`, `applied_at`), `company.tier`, `daily_runs` |
| 0007 | `location`, `location_name`, `location_macro_member`, `currency_rate`, `taxonomy_miss`, `occupation`, `occupation_domain`, `seniority`, `technology` |
| 0008 | `job_posting.locations_raw text[]` |

**No user concept anywhere.** Scores and status live on `job_posting`, so scoring is single-tenant by design. Multi-user work needs
`users`, `profiles`, `user_job_scores` and `applications` tables (Phase 1 and Phase 4 design).

The legacy SQLite `jobs.db` (1.7 GB, May 2026) is still on disk (gitignored). It's used only for the historical baseline.

## 4. Server-side serving (`src/server.py`)
| Method | Path | Params | Returns |
|---|---|---|---|
| GET | `/` | – | `templates/live.html.j2` as raw HTML (not Jinja-rendered) |
| GET | `/api/jobs` | offset, limit=50, role, work_mode, salary_min, location, level, employment_type, company_id | `{jobs:[…], total}`. Each job has DB columns plus stripped description, location, matched/missing skills, score_pct, `*_pts` |
| GET | `/api/companies` | – | `[{id,name,tier,slug,job_count}]` (unused by the UI) |
| POST | `/api/refresh` | – | Starts the crawler in the background: `{status}` |
| GET | `/api/status` | – | `{status, task_error, last_run, weights}` |

- Reads Postgres via `src/db.py`. Binds to 127.0.0.1:8080. No Dockerfile; compose provides only Postgres and Redis.
- **Missing:**
  - Authentication and authorization.
  - Users and tenancy.
  - CORS policy, rate limiting, CSRF.
  - Input validation beyond FastAPI types.
  - OpenAPI-versioned contract.
  - Health and readiness endpoints.
  - Observability.
  - Deployment config.
  - "Last updated" freshness signal.
  - Per-user scores.
- **WIP bugs** (committed as a snapshot in Phase 0, not fixed):
  - The US filter runs after the SQL `LIMIT`, so pages come back short and `total` is wrong (`server.py:234-241`).
  - Substring location matching: "india" matches Indiana, "uk" matches Milwaukee, "mexico" matches New Mexico.
  - Sorting is by `first_seen_at`, not score.
  - `/api/refresh` doesn't re-run scoring.
  - Weights are hardcoded in JS (`live.html.j2:299`).
  - Salary shows a double `$` (`live.html.j2:555`).
  - `/api/refresh` is unauthenticated, so anyone who can reach it can trigger a crawl.

## 5. Scoring (`src/ranker.py`, `src/scoring_config.py`)
| Factor | Weight | Inputs | Problems |
|---|---|---|---|
| skill | 35 | Substring hits over `SKILL_GROUPS` (~75 keywords) ×5, capped at 1 | Substrings: "go" matches almost everything, "git" matches "digital", "rag" matches "storage". The skill list is personal |
| role | 25 | `ROLE_PRIORITY` (backend 1.0 … ml 0.5, other 0.2) via `role_keywords.json` | Personal order, hardcoded |
| visa | 20 | `visa_keywords.json`: 1.0 / 0.4 / 0 | US-only. "opt"/"f1" substring false positives. **To be deleted** |
| recency | 10 | Days since `first_seen_at` | Uses first-seen date, not the real posting date |
| company | 10 | `TIER_SCORES` + `INDUSTRY_BONUS` | The industry bonus never applies (column not selected, and numeric vs string keys) |
| (hidden) | ×0.35 | Senior title or 3+ years without early-career wording | Undocumented penalty |

Shortlist: reset all statuses, then the top 50 by score excluding visa=-1. The descriptions join (`ranker.py:206`) has no locale filter, so jobs with several locales can be duplicated.

## 6. AI (`src/ai/generator.py`)
- `claude-sonnet-4-6`, 1024 max tokens, 3 concurrent calls. `verify-api` uses `claude-haiku-4-5-20251001`.
- The system prompt (profile plus resume text from PDF) is cached.
- "Never fabricate skills, roles, or metrics" is a **prompt instruction only**. Nothing in code verifies that output claims trace back to source content.
- No retry or router. JSON is extracted with a regex.
- Phase 0: the hardcoded profile was moved to `private/profile.txt` (`PROFILE_PATH`).

## 7. Hardcode inventory
State as of the start of Phase 0. ✅ means fixed in Phase 0.

### Personal data
| Where | What | Status |
|---|---|---|
| `Resume/*.pdf` (6 files) | Resumes, tracked since the first commit | ✅ moved to `private/resumes/`, purged from history |
| `docs/architecture.md:5-19` | Name, email, school, visa, research, resume table | ✅ moved to `private/`, purged from history |
| `src/ai/generator.py:24-30,45` | `_PROFILE` (name, email, school, visa, publication, role order) | ✅ loads from `PROFILE_PATH`, history redacted |
| `data/target_companies_consensus.json` | `best_resume` per company, notes naming the school and lab, NC geo fields | ✅ moved to `private/`, purged |
| `src/scoring_config.py:16,80-90`, `.env.example:9-13` | `Resume/` dir and personal resume filenames | ✅ `private/resumes` + generic names |
| CLAUDE.md (history) | Visa line, email | ✅ history redacted |
| Git commit metadata | Author email on all commits | ⚠ Not rewritten (normal git metadata). Could switch to a GitHub noreply email going forward |
| `src/scoring_config.py` `SKILL_GROUPS`, `ROLE_PRIORITY` (48-58); `generator.py:30` | The user's skill list and role order presented as product defaults | Phase 1 (move to the profile) |

### Visa / H-1B / sponsorship (Phase 2A: delete)
`data/visa_keywords.json`, `data/h1b_sponsors.json`; `ranker.py:55-64,102-107,271`; `scoring_config.py:63,105`; `generator.py` visa prompt lines;
`cli.py:29,479-520,545` (`update-h1b`, `h1b_petitions_recent`); `renderer.py:47-60`; `daily_report.html.j2:127,169`; `live.html.j2:299,528-579`;
migration 0006 columns `visa_signal`, `visa_score`; `scripts/build_csvs.py:251,303,345`; `companies.csv` column `h1b_petitions_recent`;
`tests/test_ranker.py` and `tests/test_renderer.py` visa cases.

### US assumptions (Phase 2A: generalize)
`server.py:175-206` (`_NON_US_TERMS`, `location=us`); `cli.py:183,202,248-254` (`show --us-only`, `_is_us`), `cli.py:233` ($ formatting);
`scripts/backfill_locations.py:25-160` (substring country patterns); `live.html.j2:175` ("US & Remote"), `:251-255` ($50k–$200k steps), `:359-362` (USD default).
The `job_posting` salary model is already currency-aware (`salary_currency`, `salary_period`, `salary_eur`), which is a good base for INR/LPA.

### Company allow/deny lists and tiers
`scripts/build_csvs.py:38` `TECH_INDUSTRY_IDS` and `:283-289` (industry allowlist that decides which jobseek companies are imported);
`companies.csv` `tier` → `TIER_SCORES` (`scoring_config.py:68`); `INDUSTRY_BONUS` (`:69`); `cli.py:41` `_INDUSTRY_CODES`.
**No IT-services or body-shop exclusion list exists** (the brief assumed one). Phase 2A adds opt-in user exclusions instead.

### Geographic bias
North Carolina: only in the (now private) consensus JSON. No NC logic in code.

## 8. Known bugs (not fixed in Phase 0, by design)
1. `myjobs run` bypasses the SSRF guard, UA and certifi (`src/cli.py:85`). **Security-relevant. First fix in Phase 1 or 2B (Opus).**
2. Browser boards are never processed by `myjobs run` (~120 boards).
3. `crawler board` imports a function that doesn't exist (`src/cli.py:671`).
4. `daily_runs` mixes UTC and local timestamps.
5. Scoring: substring skill matching, dead industry bonus, duplicate rows from the descriptions join.
6. Server WIP bugs (§4).
7. `scripts/backfill_locations.py` and `scripts/populate_taxonomy.py` hardcode the DSN.
8. `Retry-After` is ignored. robots.txt is never consulted for permission.
9. `tests/fixtures/google_synthetic.json` on `main` has one line replaced by `[redacted]` (side effect of the history redaction; restored on `revamp/phase-0-audit`).

## 9. Tests
- Before Phase 0: 85 tests, all pure ranker and renderer functions, 0.1 s. Nothing covered the pipeline, server, DB or generator.
- Phase 0 adds `tests/characterization/` (no-network monitor and scraper behavior pins) and a monitor-registry snapshot.

## 10. Privacy remediation performed (2026-10-11)
- Mirror backup at `~/Documents/myjobs-backup-2026-10-11.git` (outside the repo, contains the old history; delete once you're satisfied).
- `git filter-repo`: removed the `Resume/`, `docs/architecture.md` and `data/target_companies_consensus.json` paths, and replaced personal strings in all
  blobs. `main` was force-pushed once. 18 commits were re-scanned with 0 hits. GitHub showed 0 forks.
- **Residual risk:**
  - Commits up to `aa4a04d` were public before the rewrite. GitHub can keep unreachable commits viewable by SHA until it garbage-collects them. A GitHub Support "remove cached views" request finishes the job.
  - Anyone who cloned before today has the old history.
- Added a local `.git/hooks/pre-commit` (gitleaks plus `private/pii_patterns.txt`) and `.gitleaks.toml`. The allowlisted gitleaks hits are public
  client-side ATS/search keys that companies embed in their own career pages (inherited from jobseek board data).
- `.env` holds a live `ANTHROPIC_API_KEY`. It was never tracked, but a copy sits in `.history/` (an editor history folder, gitignored). Rotating the key is cheap hygiene.
