# p2-01-inr-salary
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p2-01-inr-salary` (already checked out)

## Goal
Implement `src/core/salary_inr.py` exposing `extract_inr(text: str) -> list[SalaryRange]` (import `SalaryRange` from `src/core/salary_extract.py`). It must parse Indian salary formats: LPA, lakh/lakhs/L, Cr/crore, ₹/Rs/INR prefixes, Indian digit grouping (8,00,000), and monthly figures.

## Files you may touch
- `src/core/salary_inr.py` (new). Nothing else. Do NOT edit the tests.

## Contract
`tests/test_salary_inr.py` already exists and is the spec. Read it first. Amounts are whole rupees. Yearly means period "yearly"; monthly means "monthly". Ignore amounts under ₹5,000/month or ₹1,00,000/year. Return [] when there's no INR context (₹, Rs, INR, LPA, lakh, crore).

## Acceptance
- `python3 -m pytest -q tests/test_salary_inr.py` passes.
- `python3 -m pytest -q` passes in full.
- Commit with message `feat(salary): INR/LPA extractor` (add a line `Co-Authored-By: Gemini 3.8 Flash (agy)`).

## Report back
JSON only: {"files_changed": [...], "tests": "<pytest summary line>", "assumptions": [...], "unsure": [...]}
