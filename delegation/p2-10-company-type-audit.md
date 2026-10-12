# p2-10-company-type-audit

**Model:** Gemini 3.8 Flash (agy)
**Branch:** `revamp/p2-10-company-type-audit` (create from `revamp/phase-1-feed`; do not push)

## Goal
Fix clearly wrong `company_type` tags in `data/companies.csv` (e.g. Revolut is tagged `startup`) and fill the 4 empty ones.
Change only what is clearly wrong; when in doubt, leave the tag as it is.

## Context (minimal)
`company_type` is a closed list (DECISIONS D21, `src/company_type.py`): startup, product, mnc, gcc, services, nonprofit, government.
Users filter the feed by it, so a wrong tag hides or misplaces a company. Definitions to apply:
- **startup**: private, venture-backed, usually founded within ~12 years and under ~1,500 employees (OpenAI-scale outliers stay `startup` only if still private and venture-funded).
- **product**: established company whose main business is its own product or platform, public or large private (Stripe, Atlassian, Revolut, Zomato).
- **mnc**: very large multinational (roughly 10,000+ employees across many countries), any industry (Google, Siemens, Unilever).
- **gcc**: a foreign company's captive India centre, only when the registry row is that centre itself.
- **services**: IT services, consulting, outsourcing, staffing (Infosys, Accenture, Deloitte).
- **nonprofit**, **government**: as named.

## Files you may touch (nothing else)
- `data/companies.csv`: the `company_type` column only. Do not reorder rows, change other columns, quoting or line endings.
- `docs/research/company_type_audit.md`: new. One table row per change: slug, name, old → new, one-line reason.

## Interface contract
CSV header: `slug,name,website,industry,tier,enabled,country,hq_city,company_type`. Every value must be in `COMPANY_TYPES`.
Work from your own knowledge of each company. Do not fetch websites, and do not use the network for this task.

## Acceptance criteria
- [ ] Only the `company_type` column differs: `git diff --word-diff data/companies.csv` shows no other edits.
- [ ] The empty tags are filled, and no tag outside `COMPANY_TYPES` remains.
- [ ] The audit table lists every change, with a reason.
- [ ] `python3 -m pytest -q` passes (no network).
- [ ] No personal data, no secrets.

## Report back
Branch name, commits, number of changes by old → new type, any tags you were unsure about (≤150 words).
