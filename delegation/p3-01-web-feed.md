# p3-01-web-feed
**Model:** gemini-3.8-flash-high · **Branch:** `revamp/p3-01-web-feed` (already checked out)

## Goal
Build the production feed frontend in `web/`: Next.js 15 (App Router) + TypeScript, implementing design direction **C "Field notes"**. The visual reference is `design/mockups/c-field-notes.html`: match its typography (Atkinson Hyperlegible, self-hosted via `next/font/google`), palette, spacing, sentence-style filters, row layout, light/dark themes and keyboard shortcuts. The design brief is `docs/DESIGN_BRIEF.md`.

## Files you may touch
Only `web/**`. Do not modify anything outside `web/`.

## API (already running at http://127.0.0.1:8090; OpenAPI at /api/openapi.json)
- `GET /api/v1/jobs?q=&country=IN|US|EU|APAC…&location=<geonameId>&company=<slug>&work_mode=remote|hybrid|onsite&since=1h|24h|3d|7d&cursor=&limit=50`
  → `{jobs: Job[], next_cursor: string|null}`
- `Job = {id, title, url, company:{slug,name,website,logo}, locations:[{id,name,country,type}], locations_raw:string[], work_modes:string[], employment_type, salary:{min,max,currency,period}|null, ats, first_seen_at, last_seen_at}`
- `GET /api/v1/stats` → `{active_jobs, new_last_24h, companies_hiring, last_updated, …}`
- `GET /api/v1/locations?q=ben` → `{locations:[{id,name,type,code}]}` (city chips and search)
- `GET /api/v1/jobs/{id}` → Job + `description_html` (already sanitized server-side)

In `next.config.ts`, add a rewrite `/api/:path*` → `${process.env.API_ORIGIN ?? "http://127.0.0.1:8090"}/api/:path*`, so the browser stays same-origin.

## Required behaviour
1. `/` is a server-rendered feed (fetch on the server, so the first paint has jobs). Filters live in URL query params, which makes links shareable. The default region is India (`country=IN`), with chips for Everywhere, India, US, EU and cities Bengaluru, Mumbai, Delhi NCR, Hyderabad, Pune and Chennai (resolve city ids via `/api/v1/locations` at build or request time; Delhi NCR = Delhi). Work mode, posted within (1h/24h/3d/7d), search (debounced), and a pay currency switch (native/INR/USD, stored in localStorage).
2. Rows are grouped by `timeBucket`, with relative time, title (link opens `url` in a new tab with rel noopener), company, location, work mode, salary, and "via <ATS>". "Load more" uses `next_cursor`. Add a "new since your last visit" divider, using a localStorage timestamp.
3. `/jobs/[id]` is a detail page that renders `description_html` with an "Apply on company site" button.
4. Header freshness line: "Updated 4 min ago · 394,860 open jobs · 2,569 companies".
5. Loading skeleton, empty state and error state, in the brief's human voice.
6. Keyboard: j/k move focus, Enter opens, / focuses search. Light/dark follows the system, with a toggle. AA contrast (reuse the mockup's colours).
7. `src/lib/format.ts` implements `relativeTime`, `timeBucket` and `formatSalary` exactly per the contract: copy `design/contract/format.test.ts` to `web/src/lib/format.test.ts` UNCHANGED and make it pass. Currency rates for conversion are a constant map in `src/lib/rates.ts`.
8. No UI kit, no Tailwind component libraries, no icons fonts. Plain CSS modules or one global CSS file. No purple/blue gradients, glass, emoji icons or shadowed card grids.

## Acceptance (run all; all must pass)
- `cd web && npm install && npm run build`
- `cd web && npx vitest run` (the contract tests pass)
- `cd web && npx tsc --noEmit`
- Add `web/README.md` with how to run it (`API_ORIGIN=… npm run dev`).
- Make small commits; each message ends with `Co-Authored-By: Gemini 3.8 Flash (agy)`. Don't commit `node_modules` or `.next` (add `web/.gitignore`).

## Report back
JSON only: {"files_changed_count": N, "build": "pass|fail", "vitest": "<summary>", "tsc": "pass|fail", "deviations_from_mockup": [...], "unsure": [...]}
