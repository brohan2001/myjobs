# p2-05-india-ats-research
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-05-india-ats` (already checked out)

## Goal
Research which applicant-tracking systems Indian employers use for their public careers pages, and for each one whether a public, ToS-compliant job-listing endpoint exists that we could build a crawler adapter for. Research only; write no code.

## Files you may touch
- `docs/research/INDIA_ATS.md` (new). Nothing else.

## Context
We already support: greenhouse, lever, ashby, workday, smartrecruiters, workable, recruitee, personio, rippling, pinpoint, breezy, oracle_hcm, eightfold, phenom (sitemap), plus generic sitemap/DOM/JSON-LD fallbacks (`src/core/monitors/`). Our 400 Indian candidates are in `data/candidates/india_companies.csv`; their `careers_url` column hints at which ATS they use. Count the hosts in it as evidence: e.g. `*.darwinbox.in`, `*.keka.com`, `*.zohorecruit.in`, `*.freshteam.com`, `*.myworkdayjobs.com`, `jobs.lever.co`, `boards.greenhouse.io`.

## For each candidate ATS
Darwinbox, Keka Hire, Zoho Recruit, Freshteam, greytHR (Hire), SuccessFactors, Taleo, iCIMS, Teamtailor, SmartRecruiters, Workable, Lever, Greenhouse, Workday, plus any others you find in the CSV.

Fill a table: ATS | evidence of use in India (count from the CSV plus known customers) | public careers page URL pattern | public JSON/XML/RSS endpoint (exact URL pattern, if any) | does the page embed JSON-LD JobPosting? | ToS/robots notes | adapter difficulty (S/M/L) | recommendation.

If you have web access, fetch one real public careers page per ATS, record what it returns (no login, no private APIs), and cite the URLs. If an endpoint needs auth or an API key, say "not public" and recommend JSON-LD or sitemap instead. Never suggest bypassing auth or scraping job portals (Naukri etc.).

End with a ranked "build next" list: the top 3 adapters by coverage gained per effort, each with a 3-line implementation sketch (list endpoint, pagination, fields).

## Acceptance
- The file exists, with the table covering ≥ 12 ATSs and the ranked list, under 2,000 words, citing URLs for every endpoint claim.
- Commit with message `docs: Indian ATS landscape research` and the line `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed": [...], "top3": [...], "web_access": true/false, "unsure": [...]}
