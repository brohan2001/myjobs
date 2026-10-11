# p5-01-jseek-integration
**Model:** claude-sonnet-4-6 · **Branch:** `revamp/p5-01-jseek` (already checked out)

## Goal
Draft `docs/JSEEK_INTEGRATION.md`: how the user's browser extension "JSeek" (repo at `/Users/rohanbalasubramanian/Documents/jseek-extension`, read-only for you) should connect to this portal. Design only; build nothing.

## Files you may touch
- `docs/JSEEK_INTEGRATION.md` (new) in this repo. Do NOT modify anything in the jseek-extension repo.

## Read first
- `CLAUDE.md`, `docs/REPO_MAP.md`, `docs/DECISIONS.md` here.
- In jseek-extension: `README.md`, `CLAUDE.md`, `GOALS.md`, `manifest.json`, `background.js`, `content_script.js`, `site_configs.js`, `server.js`, `docs/`. Skim as needed and summarise what it actually does. Note: it runs on jseek.co, which belongs to the third-party "jobseek" project that this portal's crawler was forked from (MIT).

## Must cover
1. What JSeek does today (verified from code): DOM scraper, autofill, LLM router (count the models and describe the circuit breaker), LaTeX resume grafting, how it stores the profile and where it sends data.
2. A shared profile schema: fields both sides need. Propose a JSON Schema sketch.
3. Flows:
   - The extension pulls the user's profile and a tailored resume PDF from the portal.
   - "Applied" status flows back to a tracker.
   - The extension captures a job from a page the server can't scrape (e.g. LinkedIn or Naukri pages the user views in their own session). It sends the URL and the user-visible fields only, never bulk scraping. Address the ToS risk explicitly.
4. Auth between extension and portal: compare an OAuth2 PKCE flow, a device code flow and a personal access token. Cover token storage in `chrome.storage`, scopes, revocation and CSRF/CORS.
5. A minimal API contract draft (OpenAPI-style table): `GET /v1/me/profile`, `GET /v1/jobs/{id}/resume.pdf`, `POST /v1/applications`, `POST /v1/captures`, `GET /v1/applications`. Include request/response shapes and rate limits.
6. A duplication audit: scraper ideas, the LLM router and LaTeX grafting that appear in both repos. Should a shared package be extracted (Python vs JS split)? Give a recommendation.
7. Risks and open questions.

## Acceptance
- The file exists, has all 7 sections, contains claims about JSeek grounded in the code (cite file paths) and is under ~2,500 words.
- Commit with message `docs: Phase 5 JSeek integration design (draft)` and the line `Co-Authored-By: Claude Sonnet 4.6 (agy)`.

## Report back
JSON only: {"files_changed": [...], "jseek_summary": "<2 sentences>", "recommendation": "<one line>", "unsure": [...]}
