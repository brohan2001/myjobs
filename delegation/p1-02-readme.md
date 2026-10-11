# p1-02-readme
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p1-02-readme` (already checked out)

## Goal
Write the public `README.md` for this repo, which is now a public feed of the latest jobs from company career pages, worldwide with an India focus. The audience is a developer or recruiter landing on GitHub.

## Files you may touch
- `README.md` (new). Nothing else.

## Read first
`CLAUDE.md`, `docs/REPO_MAP.md`, `docs/DECISIONS.md`, `docs/SCRAPING_REPORT.md` (sections 1–6), `docs/INFRA_PROPOSAL.md` §6, `THIRD_PARTY_NOTICES.md`, and `git log --oneline -40`.

## Content (concise, ≤ 900 words, written like a person, no marketing fluff, no emoji, no badges wall)
1. One-paragraph what and why: a continuously updated feed of jobs from ~3,000 company career boards (Greenhouse, Lever, Ashby, Workday, …) with India as the default lens. Public, read-only, no sign-up.
2. How it works: a short diagram in a code block (CSV registry → sync → Redis queues → worker monitors/scrapers → Postgres → FastAPI → Next.js), plus 4–6 bullets on the interesting parts (per-domain rate limits, SSRF guard, robots.txt, GeoNames locations, INR/LPA salary parsing, discovery pipeline with a review queue).
3. Quick start: the docker compose, alembic, load_geonames, populate_taxonomy, `myjobs worker`, `myjobs serve` and `web/` dev commands, all taken from CLAUDE.md. Mention that `.env.example` is the env template.
4. API: a table of `/api/v1/jobs` params and the other endpoints, plus a curl example (`?country=IN&since=24h`).
5. Respectful crawling: public ATS APIs preferred; robots.txt honoured for site-reading monitors; no scraping of portals whose ToS forbid it (Naukri, LinkedIn…); per-domain rate limits.
6. Status and roadmap: link to `docs/REVAMP_PLAN.md`. Per-user profiles and resume tailoring come later.
7. Credits and licence: the crawler core is derived from colophon-group/jobseek (MIT), and location data is GeoNames (CC-BY 4.0). See THIRD_PARTY_NOTICES.md. Say that the project's own licence is not yet chosen.

No personal information about the repo owner (no names, emails, schools, visa status).

## Acceptance
- `README.md` exists, ≤ 900 words, with all 7 sections. Every command in it appears in CLAUDE.md or the docs.
- Commit with message `docs: public README` and the line `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed": ["README.md"], "words": N, "unsure": [...]}
