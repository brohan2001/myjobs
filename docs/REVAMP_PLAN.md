# Revamp plan

Goal: a multi-user job portal that covers the world and is strongest for India, built on the existing jobseek-derived pipeline. This is a refactor-and-extend, not a rewrite.
Every phase runs on its own `revamp/<phase>` branch and ends with green tests and a report: what changed, what was deliberately not done, risks, and what's needed from the user.

**Effort:** S = under a day, M = 1–3 days, L = more than 3 days of focused agent and review time.
**Owner tags:**
- **[O]** Opus (orchestrator): architecture, schema, security-sensitive code, review.
- **[S]** Sonnet subagent in Claude Code: medium tasks that need repo context.
- **[A:flash]**, **[A:sonnet]**, **[A:opus]**: agy tasks, small and independent, with a brief in `delegation/`.
- Rule: auth, tenancy, SSRF, PII/encryption, the profile schema and all integration are **[O]**. Delegated output is always reviewed by diff.

---

## Status (2026-10-11, end of autonomous session)
| Phase | State | Notes |
|---|---|---|
| 0: Audit, privacy, plan | Done | Approved. PII purged from history |
| 1: Public latest-jobs feed (revised, D10) | Done | Continuous worker, GeoNames, public API, coverage endpoint, robots.txt, Workday and WIP fixes |
| 2A: Remove US assumptions, India model | Mostly done | Visa/H1B deleted, GeoNames with Indian aliases and ASCII names, INR/LPA salary. Open: notice period, experience bands, company-type taxonomy in the API |
| 2B: Scraping and India expansion | In progress | Discovery pipeline with a review queue; 400 Indian candidates being verified; 16+ lost boards recovered. Open: Indian ATS adapters (needs research), A/B test of the User-Agent (D14) |
| 3: UI | Built (direction C, D15) | Next.js feed, detail and coverage pages. The user may still swap the direction |
| 4: Infra proposal | Draft done | docs/INFRA_PROPOSAL.md. Awaiting the user's approval before anything is deployed |
| 5: JSeek integration | Design draft done | docs/JSEEK_INTEGRATION.md |
| Later: profiles, per-user scoring, tailoring | Not started | Deferred by D10 |

## Phase 0: Audit, privacy, baseline (this phase)
Delivered: `AUDIT.md`, `SCRAPING_REPORT.md`, `REPO_MAP.md`, `DECISIONS.md`, this plan, the PII history purge, the MIT notice, a pre-commit PII/secret guard, the baseline snapshot tool,
and characterization tests. **Still open:** a *live* baseline run, which needs Docker (see Phase 1 task 1.0).

## Phase 1 (revised 2026-10-11, see DECISIONS D10): Public latest-jobs feed (M)
Done on `revamp/phase-1-feed`:
- Removed the reports, shortlist scoring, AI generation and visa/H1B logic.
- Continuous worker (`myjobs worker`), with the SSRF-bypass fix.
- GeoNames loader.
- Public read-only API (`/api/v1/jobs|companies|locations|stats`) and an interim page.
- Migration 0009.
- API tests.

Remaining feed work, in priority order:
1. Workday multi-site error swallowing: surface it as a board failure.
2. Re-resolve `location_ids` for postings enriched before GeoNames existed.
3. Run the browser worker on a schedule.
4. Stale-job expiry visibility.
5. Phase 3 UI.

## Later phase: Generic profile system and per-user scoring (L), deferred by D10
Exit criteria:
- No personal data in tracked code.
- The sample profile drives the whole pipeline.
- Scores are per user.
- Resume tailoring only selects and reorders real content.

| # | Task | Owner | Effort |
|---|---|---|---|
| 1.0 | Live baseline: `docker compose up`, run, `scripts/baseline_snapshot.py`, commit `docs/baseline/<date>` | [S] (user starts Docker) | S |
| 1.1 | Fix the `myjobs run` client bypass: use `create_http_client` (SSRF transport, honest UA, certifi) for every board; characterization tests stay green | [O] | S |
| 1.2 | Profile schema (Pydantic + JSON Schema): identity, contact (private), education, experience, projects, skills (with self-assessed depth), publications, preferences (roles, regions, cities, work mode, salary floor + currency, notice period, experience band, include/exclude lists, scoring weights), resume sources. Every bullet carries `source_ref` and a `verified` flag | [O] | M |
| 1.3 | Repository interfaces (`ProfileRepo`, `JobRepo`, `ScoreRepo`, `ApplicationRepo`) over Postgres. Migration 0009: `app_user`, `profile` (JSONB + version), `resume_file` (encrypted blob ref), `user_job_score`, `application`. Scores move off `job_posting` | [O] | M |
| 1.4 | `examples/sample.profile.yaml`: a fictional Bengaluru-based backend engineer with plausible but clearly fake data | [A:sonnet] | S |
| 1.5 | Loader: `private/<name>.profile.yaml` → DB. Seed the real profile from the master `.tex` resume and profile notes in `private/` (local only) | [O] | S |
| 1.6 | Resume ingestion: PDF (pdfplumber/pypdf), DOCX (python-docx), LaTeX (section-aware parser) → raw text → LLM structured extraction into the schema → **review/edit diff screen** (nothing is saved without user confirmation; low-confidence fields highlighted) | [S] parsers, [O] extraction prompt and contract | M |
| 1.7 | Resume output: Jinja-LaTeX template renderer. The selector picks the most relevant projects and skill lines by job similarity, keeps a 1-page limit (compile with tectonic/latexmk, shrink loop). The user's master `.tex` becomes the template and seed | [S] renderer, [O] selection rules | M |
| 1.8 | **No-fabrication guard:** tailoring returns references to `source_ref` bullets plus optional rephrasing. A validator rejects any number, metric, employer, title or skill not present in the source bullet; unverified metrics are flagged in the UI | [O] | M |
| 1.9 | Per-user scoring: the 5 factors become pluggable. Weights and thresholds come from preferences. Token-boundary skill matching against the profile's skills. The hidden senior multiplier is replaced by a preference-driven experience band. The visa factor goes behind a flag until 2A deletes it | [S] against [O] spec | M |
| 1.10 | Tests: schema round-trip, parsers on fixture resumes (synthetic), validator red-team cases, scoring per profile | [S] | M |

Risk: LLM extraction quality on LaTeX/PDF, mitigated by the review screen. Resume PII is stored in plaintext until 1.3 lands, mitigated by local-only use until then.

## Phase 2A: Remove US assumptions, India-ready data model (M)
| # | Task | Owner | Effort |
|---|---|---|---|
| 2A.1 | **Delete** visa/H1B: code, `visa_keywords.json`, `h1b_sponsors.json`, `update-h1b`, UI copy, tests. Migration drops `visa_signal`, `visa_score`, `h1b_petitions_recent`. Optional worldwide "work authorization / eligible countries" preference | [S] with [O] review | M |
| 2A.2 | Include/exclude lists (company, company type, keyword) in preferences. Opt-in editable presets (e.g. "large IT services") stored as data, not code | [S] | S |
| 2A.3 | Salary normalization: INR/LPA ("10-15 LPA", "₹12L", "12 lakh", "1.2 Cr", monthly ₹ figures, CTC vs in-hand), multi-currency via `currency_rate`, an explicit "not disclosed" state. Builds on `salary_extract.py` | [S] parser, [A:flash] fixtures (200 real-format strings) | M |
| 2A.4 | City and country aliases: Bengaluru/Bangalore, Gurugram/Gurgaon, Mumbai/Navi Mumbai/Thane, Delhi NCR (Noida, Ghaziabad, Faridabad), Chennai/Madras, Kolkata/Calcutta, Pune/PCMC, Hyderabad/Secunderabad/Cyberabad, Kochi/Cochin… Feeds `location_resolve.py` and `location_name`. Replaces the substring country matching (fixes the Indiana bug) | [A:flash] table, [S] integration | S |
| 2A.5 | Work mode (remote/hybrid/onsite), notice period and immediate-joiner extraction, experience bands, company-type taxonomy (startup / product / MNC / GCC / services) | [S] | M |
| 2A.6 | Region becomes a filter and ranking preference; India is the default preset. No non-India data is deleted | [S] | S |

Risk: deleting visa logic changes scoring outputs, so the characterization snapshots for the ranker get updated deliberately in the same commit.

## Phase 2B: Scraping research and India company expansion (L, highest value)
Prerequisite: the live baseline (1.0) is committed. Every scraper change must keep characterization tests green, or update them deliberately with an explanation.

| # | Task | Owner | Effort |
|---|---|---|---|
| 2B.1 | Politeness layer (pending Q1): robots.txt permission check with caching, honest UA `myjobs-bot/<ver> (+repo URL; contact)`, `Retry-After`, per-host concurrency cap, ETag/If-Modified-Since. Stealth off by default. Boards that become disallowed are quarantined and reported | [O] | M |
| 2B.2 | Browser worker in the daily run (or an explicit schedule) so the ~120 browser boards aren't silently dropped | [S] | S |
| 2B.3 | Research: discovery/detection best practice (URL and markup fingerprints, JSON-LD JobPosting as a discovery source, sitemaps, public JSON endpoints). Output: ranked improvement list (coverage per effort) vs `SCRAPING_REPORT.md` | [S] research | M |
| 2B.4 | Research the Indian ATS landscape: verify which platforms are actually used (Darwinbox, Keka, Zoho Recruit, Freshteam, greytHR, Workable, Recruitee, SmartRecruiters, Lever, Teamtailor, custom pages). For each: public endpoint? ToS? adapter difficulty? | [S] research, [A:flash] per-ATS summaries | M |
| 2B.5 | Build adapters for the top 2–4 Indian ATS platforms with public, ToS-compliant endpoints. Each gets fixtures and characterization tests | [S] each (disjoint files) | M each |
| 2B.6 | Indian company sources: list lawful sources (startup directories, unicorn/soonicorn lists, NSE/BSE listed companies, accelerator/incubator portfolios, GCC lists) with license/ToS status per source. Target size set *after* research | [S] research, [A:flash] tabulation | M |
| 2B.7 | Discovery pipeline: candidate → careers URL (`career_discover.py`) → ATS detect (`detect_monitor_type`) → validate (HTTP OK, robots allowed, parses to ≥1 real job) → tag (country, city, type, size band, ATS) → dedupe → **review queue** → registry. Wraps the existing jobseek code instead of rewriting it | [O] design, [S] implementation | L |
| 2B.8 | Health: per-adapter and per-company failure tracking (exists partly), automatic quarantine (exists: 5 strikes), alerts (new), coverage report/dashboard (companies by country/city/ATS, health, last success) | [S] | M |
| 2B.9 | Registry conversion: discovered companies → `companies.csv`/`boards.csv` rows (adding a `country`, `city`, `company_type` column set) | [A:flash] | S |

### Source policy (applies to every source we add)
| Source type | Status | Risk |
|---|---|---|
| Public ATS candidate APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Workday cxs) | Allowed, preferred | Low. These endpoints exist so candidates can see jobs. Honor rate limits |
| Company career pages / sitemaps / JSON-LD | Allowed if robots.txt allows | Low to medium. Honor robots and TDM |
| Naukri, LinkedIn, Indeed, Glassdoor, foundit, Instahyre, Cutshort, Wellfound pages | **Do not scrape** (ToS forbid it; LinkedIn litigates) | High. Alternatives: official partner APIs where they exist, user-pasted URLs, the JSeek extension reading the page in the user's own browser session |
| Startup/funding directories (Tracxn, Crunchbase, Inc42) | Paid or ToS-restricted. Use only public pages or official exports where the license allows | Medium. Record the license for each source |
| Government and public lists (NSE/BSE listings, Startup India/DPIIT recognized startups) | Generally usable; verify the terms of each | Low |

## Phase 3: UI/UX redesign (L), propose first
3.0 Design brief and **3 distinct visual directions** with rough HTML/CSS mockups of the feed screen → **stop for the user's pick**.
Then: Next.js (App Router) + TypeScript frontend, FastAPI as the API, the Python worker unchanged (pending Q4). Screens: onboarding (upload → review → preferences),
ranked feed (why-this-job, score breakdown, quick actions), job detail + tailor flow + preview, tracker, profile editor, preferences/exclusions, coverage/health.
Mobile-first, fast first paint, light and dark themes, keyboard navigation, accessible contrast, LPA formatting with currency switching, city chips with aliases.
Owners: [O] direction, information architecture and API contract; [S] components against the spec; [A:sonnet] mockup variants.

## Phase 4: Infra proposal (proposal only until approved)
`docs/INFRA_PROPOSAL.md`, covering:
- Postgres hosting (Supabase vs Neon vs a VPS) with RLS-based per-user isolation and the target multi-tenant schema.
- Redis (Upstash vs self-hosted) or a Postgres queue.
- Worker hosting (GitHub Actions cron vs Fly/Railway/Render vs a ₹-cheap VPS), cadence per source tier, stale-job expiry, alerting, a "last updated" indicator.
- Frontend hosting, the auth provider, resume storage with encryption at rest, secrets, observability.
- LLM cost model (BYOK plus a demo quota; a Haiku-class model for bulk work, a Sonnet-class model for tailoring; a circuit-breaker router).
- A recommended option with monthly ₹ cost. Owner: [O].

## Phase 5: JSeek integration design (design only)
`docs/JSEEK_INTEGRATION.md`: shared profile schema, extension ↔ portal auth (OAuth device flow or a PKCE token), API contract draft
(`GET /v1/me/profile`, `GET /v1/jobs/{id}/resume.pdf`, `POST /v1/applications`), applied-status flow-back, and what the extension does where server-side scraping is off-limits.
Duplication audit: the extension's LLM router, LaTeX grafting and DOM scraper vs MyJobs, and whether a shared package is worth it. Owner: [O], with an [S] exploration of the extension repo.

---

## Top risks
1. **Coverage regression from the politeness changes** (robots, honest UA). Mitigation: quarantine and report instead of silent loss; the user decides (Q1).
2. **Indian ATS endpoints may be private or ToS-restricted.** Mitigation: research before building; fall back to career-page JSON-LD.
3. **PII in a multi-user system.** Mitigation: encryption at rest for resumes, RLS, export/delete endpoints and audit logging, all owned by [O].
4. **LLM fabrication.** Mitigation: the structural validator (1.8), not just prompt rules.
5. **Upstream drift.** We've forked jobseek, so we no longer get its monitor fixes automatically. Mitigation: record the fork point; cherry-pick upstream monitor fixes periodically (MIT allows it).
6. **Cost:** Playwright boards and LLM scoring. Mitigation: cheap model for bulk work, caching, browser boards on a slower cadence.
