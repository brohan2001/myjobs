# p4-01-infra-proposal
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p4-01-infra` (already checked out)

## Goal
Draft `docs/INFRA_PROPOSAL.md`: how to deploy this system for a solo developer in India on a small budget (costs in ₹ per month; free or cheap tiers preferred). This is a proposal only; build nothing.

## Files you may touch
- `docs/INFRA_PROPOSAL.md` (new). Nothing else.

## Facts about the system (read `CLAUDE.md`, `docs/REPO_MAP.md`, `docs/DECISIONS.md` D10–D16 for detail)
- Python worker: a long-running process (`myjobs worker`), ~40 async workers. Some boards need Playwright Chromium (~120 boards; ~1 GB RAM when active). It crawls ~3,100 boards hourly with per-domain rate limits.
- Postgres 16: ~400k active postings now, growing (estimate 2–5 GB with descriptions). Needs pg_trgm. Redis 7 for queues (small).
- FastAPI read-only public API. Next.js frontend in `web/`.
- Later: user accounts, resumes (sensitive PII, needs encryption at rest), per-user scoring, LLM use (resume tailoring).

## Must cover
1. Options compared in a table with ₹/month:
   - **Database:** Supabase, Neon, a self-hosted VPS, Railway.
   - **Worker:** an always-on VPS (Hetzner, Oracle Cloud free tier ARM, DigitalOcean/Linode Bangalore), Fly.io, Railway, Render, or GitHub Actions cron. GitHub Actions is likely unsuitable for an always-on crawler; explain why.
   - **Frontend:** Vercel or Cloudflare Pages.
   - **API:** co-located with the worker vs separate.
   - **Redis:** Upstash vs self-hosted.
2. A target multi-tenant schema sketch for later: users, profiles, resumes, preferences, companies, sources, jobs with canonical/dedupe keys, per-user scores, applications, pipeline runs. Cover per-user isolation via Postgres RLS, and the migration path from today's schema (alembic).
3. Continuous updates:
   - cadence per board tier (hot companies every 15–30 min, long tail every 6–12 h);
   - politeness;
   - stale-job expiry;
   - failure alerting (healthchecks.io or similar);
   - the "last updated" indicator (it already exists in `/api/v1/stats`).
4. Auth options for later (Supabase Auth, Clerk, Auth.js), resume storage with encryption at rest, secrets management, backups, observability (logs/metrics with free tiers).
5. LLM cost model for later: bring-your-own-key vs server key with per-user quotas; a cheap model for bulk work and a strong one for tailoring; prompt caching; a fallback router.
6. **Recommendation:** one concrete stack, a monthly ₹ estimate (low/expected), and the first 5 steps to deploy.
- Mark every price "as of your knowledge cutoff; verify before buying". Don't invent precise numbers you aren't sure of; give ranges.

## Acceptance
- The file exists, has all 6 sections and is under ~2,500 words.
- Commit with message `docs: Phase 4 infra proposal (draft)` and the line `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed": [...], "recommendation": "<one line>", "monthly_inr_estimate": "<range>", "unsure": [...]}
