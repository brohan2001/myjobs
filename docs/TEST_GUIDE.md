# Test guide: what to try, and what to keep or cut

Use this to test the product and decide what stays. Fill in the **Verdict** column with keep, cut or change (plus a note), then
hand it back. Nothing listed here has been removed yet.

## Start it
```bash
docker compose up -d                      # Postgres + Redis
myjobs worker                             # crawler (separate terminal; Ctrl-C stops it)
myjobs serve --port 8090                  # API, docs at http://127.0.0.1:8090/api/docs
cd web && API_ORIGIN=http://127.0.0.1:8090 npm run dev   # feed at http://localhost:3000
```

## 1. The web feed (what end users see)
| # | Feature | How to try it | Verdict |
|---|---|---|---|
| 1 | Latest-jobs feed, newest first, endless "more" | Open `/` and scroll | |
| 2 | Place filter (India default; country, region, city) | Click the place word in the sentence | |
| 3 | Work-mode filter (remote / hybrid / onsite) | Sentence filter | |
| 4 | Company-type filter (startup, product, MNC, GCC, services…) | Sentence filter | |
| 5 | Experience filter (max years) | Sentence filter | |
| 6 | Notice-period filter | Sentence filter | |
| 7 | Time window (last 24h / week…) | Sentence filter | |
| 8 | Keyword search | Search box | |
| 9 | INR salary display (LPA), when a posting has a salary | Look for salary on rows | |
| 10 | Company-run collapsing (many jobs from one company fold into one row) | Feed rows with "+N more" | |
| 11 | Job detail page (description, location, apply link) | Click a job | |
| 12 | Coverage page (companies and boards by country/ATS) | `/coverage` | |
| 13 | Light/dark theme toggle | Header | |
| 14 | Sidebar notes | Right column on desktop | |

## 2. Public API
| # | Feature | Verdict |
|---|---|---|
| 15 | `GET /api/v1/jobs` with filters q, country, location, company, work_mode, since, seniority, occupation, max_years, company_type, notice_days; keyset cursor | |
| 16 | `GET /api/v1/jobs/{id}` | |
| 17 | `GET /api/v1/companies`, `/locations`, `/stats`, `/coverage` | |
| 18 | Rate limiting and CORS (`API_RATE_LIMIT_PER_MINUTE`, `API_CORS_ORIGINS`) | |
| 19 | Old interim page served by the API at `/` (`src/api/static/`), superseded by `web/` | |

## 3. Operator commands
| # | Command | What it does | Verdict |
|---|---|---|---|
| 20 | `myjobs worker` | Continuous crawl, about hourly per board (browser boards too) | |
| 21 | `myjobs crawl` | One pass, then exit | |
| 22 | `myjobs serve` | API | |
| 23 | `myjobs stats` | Freshness and coverage summary | |
| 24 | `myjobs health` | Alerts (stale feed, worker lag, boards gone, ATS failures); exits 1 on alert | |
| 25 | `myjobs sync` | CSV registry → Postgres + Redis | |
| 26 | `myjobs company list/add/disable` | Edit the registry | |
| 27 | `myjobs prune-scrape-queues` | Housekeeping for the scrape queues | |
| 28 | `scripts/discover_companies.py` | Candidate companies → verified boards (`--rediscover` for boards that went away) | |
| 29 | `scripts/triage_review.py` | Walk the discovery review queue by hand | |
| 30 | `scripts/baseline_snapshot.py` | Coverage snapshot into `docs/baseline/` | |
| 31 | `scripts/ua_ab_test.py` | User-Agent A/B test (D14 is decided now) | |
| 32 | `scripts/load_geonames.py`, `scripts/populate_taxonomy.py` | One-time setup | |

## 4. Background enrichment (no UI of its own)
| # | Feature | Verdict |
|---|---|---|
| 33 | Location resolution (GeoNames, Indian city aliases) | |
| 34 | Salary extraction (INR/LPA, multi-currency) | |
| 35 | Seniority and occupation tags | |
| 36 | Notice-period extraction (separate loop beside the worker) | |
| 37 | robots.txt checks for site-reading boards; honest User-Agent with a Chrome allowlist | |

## 5. Suspected bloat (my read; your call)
| # | What | Why I suspect it | Verdict |
|---|---|---|---|
| A | Most of `src/workspace/` (about 17k lines, including 9k in `commands/`) | Fork leftovers: jobseek's workspace CLI. Only `career_discover` and `_compat` are used outside it | |
| B | `src/api/static/` interim page | Replaced by `web/` | |
| C | `scripts/build_csvs.py`, `fix_workday_sites.py`, `probe_jobseek_monitors.py` | One-off migration and probe scripts | |
| D | `src/ai/` | Empty (only a `__pycache__`) | |
| E | `scripts/ua_ab_test.py` | The decision is made; the results are in `docs/research/ua_ab/` | |
| F | Seniority/occupation filters in the API but not in the web UI | Either expose them or drop them | |

## 6. Missing features you might want
Write down anything you looked for and didn't find (e.g. saved searches, email alerts, "hide this company", visa or location
eligibility, apply tracking).
