# p3-03-company-collapse
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p3-03-company-collapse` (already checked out)

## Goal
A single high-volume employer (for example a bank posting 50 branch roles at once) can flood the top of the feed. Collapse runs from one company so the feed stays scannable.

## Files you may touch
Only `web/**`. Do not change `web/src/lib/format.test.ts`.

## Contract
- A new pure function in `web/src/lib/collapse.ts`: `collapseRuns(jobs: Job[], keep = 2): Array<{ kind: "job"; job: Job } | { kind: "more"; company: { slug: string; name: string }; count: number; hidden: Job[] }>`.
- Within each time bucket, when 3 or more jobs from the same company appear consecutively, keep the first `keep` and replace the rest with one `more` item.
- Order is preserved. Non-consecutive jobs from the same company are not merged.
- Tests in `web/src/lib/collapse.test.ts`, with at least 8 cases: no runs, a run of exactly 3, a long run, two separate runs, `keep=1`, an empty list, a run at the end, and interleaved companies.
- UI: render a `more` item as a quiet row reading "+48 more from Kotak Mahindra Bank". Clicking it expands the hidden rows in place. A secondary link "only this company" goes to `/?company=<slug>` while keeping the other filters. Make it keyboard accessible (j/k must still work).
- "Load more" pages must collapse correctly at page boundaries: a run continuing from the previous page must keep collapsing.

## Acceptance
- `cd web && npm install && npx vitest run && npx tsc --noEmit && npm run build`, all passing.
- Small commits, each ending with `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed_count": N, "vitest": "<summary>", "build": "pass|fail", "unsure": [...]}
