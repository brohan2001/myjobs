# p3-02-web-polish
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p3-02-web-polish` (already checked out)

## Goal
Polish the feed frontend in `web/` (direction C "Field notes"; reference `design/mockups/c-field-notes.html`). The API runs at http://127.0.0.1:8090. For a dev server use `cd web && npm install && API_ORIGIN=http://127.0.0.1:8090 npm run dev -- -p 3200`.

## Files you may touch
Only `web/**`. Do NOT change `web/src/lib/format.test.ts` (the contract) or anything outside `web/`.

## Changes
1. **Location relevance:** when a region or city filter is active, show the job's location that matches it first. Use `locations[].country` (ISO2) for the country filters IN/US, and the EU member list for EU. For a city filter, match by name. Example: under "India", a job in [Houston, US; Jaipur, IN] must render "Jaipur, India +1". Implement this as a pure function `orderLocations(locations, filter)` in `web/src/lib/locations.ts` with vitest tests in `web/src/lib/locations.test.ts` (at least 6 cases).
2. **Work-mode copy:** show "Remote", "Hybrid" or "On-site" from `work_modes`. Show nothing when the array is empty, never "undefined".
3. **ATS label:** map `ats` to human names (greenhouse → Greenhouse, lever → Lever, ashby → Ashby, workday → Workday, smartrecruiters → SmartRecruiters, workable → Workable, dom/sitemap/nextdata/api_sniffer/inline/null → "Career site"). Make it a pure function with tests.
4. **Coverage page** `/coverage`: fetch `GET /api/v1/coverage` → `{by_ats:[{ats,boards,healthy,failing,gone,last_success_at}], by_country:[{country,companies,companies_hiring}], india_by_city:[{city,companies}]}`. Render plain tables in the same visual language, with a one-line human intro ("Where these jobs come from, and how healthy each source is."). Link to it from the footer.
5. **Footer:** "Jobs come from public company career pages. Updated continuously." plus links to Coverage and the GitHub repo https://github.com/brohan2001/myjobs.
6. **Performance:** add `export const revalidate = 30` (or the equivalent fetch cache settings) so the server doesn't refetch on every request. Keep the first-load JS at or below its current size (~112 kB).

## Acceptance (all must pass)
- `cd web && npx vitest run` (contract and new tests)
- `cd web && npx tsc --noEmit`
- `cd web && npm run build`
- Small commits, each ending with `Co-Authored-By: Gemini 3.8 Flash (agy)`.

## Report back
JSON only: {"files_changed_count": N, "vitest": "<summary>", "tsc": "pass|fail", "build": "pass|fail", "first_load_js_kb": N, "unsure": [...]}
