# Plan

Goal: a public feed of the latest **tech** jobs (D27), worldwide and strongest for India, with at least jseek.co's coverage
(D28), hosted for ₹0 (D24). Per-user profiles come later (D10).

## Done
| Phase | What |
|---|---|
| 0 | Audit, PII history purge, characterization tests |
| 1 | Continuous worker, GeoNames locations, public API, robots.txt |
| 2A | Visa/H1B removed; Indian city aliases, INR/LPA salary, company type (D21), experience filter |
| 2B | Keka, greytHR and Zoho Recruit adapters; discovery and triage; `myjobs health` (D23); honest UA (D14) |
| 3 | Next.js feed (direction C, D15) |
| Cleanup | Bloat cut from the 2026-10-14 test pass (D26) |

## Now (approved 2026-10-15, in order)
1. **Crawler scheduling.** Board checks are claimed before job-page scrapes; daily re-scrapes stop; shutdown is bounded.
   `myjobs boards <company|ats>` shows when each board was last checked.
   *Why:* 2,371 of 2,845 boards were over 2 h overdue on 2026-10-14 because the scrape backlog starved board checks.
2. **Core re-sync with jobseek.** Vendor jobseek's current core with all its monitors and scrapers (portal ones included,
   D25). Strip the Go and metrics paths; keep our robots, UA, SSRF and Indian adapters.
3. **Registry import plus tech vetting (D27).** Import jobseek's ~7,900 boards. Keep a company only if it has tech postings,
   and drop non-tech postings at ingest. Measure the title classifier on 300 titles first.
4. **Parity proof (D28).** `scripts/jseek_parity.py` samples jseek.co's public search and reports misses by cause.
5. **Feed accuracy and UI.**
   - Store and show the real posting date (it's parsed today but discarded).
   - Make `≤2 years` exclude senior/staff/principal titles.
   - Fix the "bang" location search.
   - Search only on Enter.
   - Denser rows.
6. **Ship.** Deploy kit per `docs/DEPLOY.md`.

## Later (D10)
Accounts, profiles, per-user scoring, resume tailoring (never fabricating content); JSeek extension integration
(`docs/JSEEK_INTEGRATION.md`).
