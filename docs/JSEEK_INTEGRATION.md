# JSeek Integration Design

> Design document only — nothing is built yet. Decisions recorded here become
> DECISIONS.md entries once accepted.

---

## 1. What JSeek Does Today

JSeek Enhancer (v1.3.0, `manifest.json`) is a Manifest V3 Chrome extension
that runs on **jseek.co and 18 other job platforms** (`manifest.json`
`host_permissions`). It has three cooperating pieces:

**DOM scraper / UI injector** (`content_script.js`, `site_configs.js`).
`detectSite()` maps the current hostname to one of 18 named `SITE_CONFIGS`
objects (LinkedIn, Greenhouse, Workday, Lever, etc.) or falls back to
`SITE_CONFIGS.universal`, whose heuristic scorer ranks content blocks by text
density × JD-keyword hits × log(length). Selectors for job description, title,
company name and ATS form fields are declared per platform. A `MutationObserver`
re-runs on SPA navigation. The content script injects a button row above each
job description and fills ATS forms via `setFieldValue`, which uses the native
prototype value setter and dispatches `InputEvent` with `composed: true` to
bypass React's fiber shim.

**Profile storage.** `DEFAULT_PROFILE` (29 fields: name, email, phone,
LinkedIn, GitHub, address, work authorisation, education, salary, EEO fields)
is hard-coded in `content_script.js:4–32`. The user-saved copy lives in
`chrome.storage.local` under the key `profile` and is merged with
`DEFAULT_PROFILE` at `init()`. Job states (`JOB_STATES`) and the LLM provider
choice are also persisted in `chrome.storage.local`.

**LLM router + LaTeX resume grafting** (`server.js`). A local Express server
on `http://localhost:4567` exposes `/tailor`, `/cover-letter`, `/cold-message`,
and `/cold-email`. Each endpoint accepts a job description (and optionally a
provider), builds a prompt against `resumes/swe.tex`, and calls an LLM. Two
providers are supported:
- `claude` — invokes the Claude CLI subprocess.
- `relay` — calls **RelayFreeLLM** on `localhost:8000` via `callRelay(prompt,
  primaryModel)` (`server.js:466`). RelayFreeLLM's `model_dispatcher.py` runs
  a **19-model cascade** (documented in `docs/routing-hierarchy.md`). The
  primary models are `google/gemini-3.5-flash` (resume/cold) and
  `cerebras/zai-glm-4.7` (cover letter). On any `ProviderError`,
  `RateLimitError`, or `AuthenticationError`, the dispatcher applies a
  **circuit breaker** with a 60-second cooldown for rate-limit errors and a
  30-second cooldown for other errors (`model_selector.py`), then tries the next
  model in rank order. All 19 must fail before the error propagates back to Node.

LaTeX grafting: the LLM returns a complete `swe.tex`; `extractLatex()` strips
any prose wrapper; `graftPreamble()` re-attaches the original document preamble
(`server.js:222–260`). The tailored `.tex` compiles in `resumes/build/` via
`pdflatex -interaction=nonstopmode`. The master `swe.tex` is never overwritten
mid-flight. A production trimmer (`trimToWord`, `visibleLength`,
`applySkillsLineTrimmer`) clamps skill rows to ≤105 visible characters before
writing. Every successful tailor/CL request is appended to
`resumes/applied_jobs.json` via `appendLedger()`.

**Batch apply queue** (`background.js`). A service-worker queue opens each
selected job's ATS URL in a background tab, tells the content script to tailor
+ fill + (optionally) submit, then logs the result to `POST /applications/log`
on the local server (best-effort). One tab at a time to avoid racing the
`/tailor → /cover-letter` serialised pipeline.

---

## 2. Shared Profile Schema

Both sides need a common representation so the extension can pull its profile
from the portal instead of relying on `DEFAULT_PROFILE` hard-coded in source.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://myjobs.example/schemas/profile/v1.json",
  "title": "UserProfile",
  "type": "object",
  "required": ["id", "name", "email"],
  "properties": {
    "id":                  { "type": "string", "format": "uuid" },
    "name": {
      "type": "object",
      "required": ["first", "last"],
      "properties": {
        "first": { "type": "string" },
        "last":  { "type": "string" }
      }
    },
    "email":               { "type": "string", "format": "email" },
    "phone":               { "type": "string" },
    "linkedin_url":        { "type": "string", "format": "uri" },
    "github_url":          { "type": "string", "format": "uri" },
    "location": {
      "type": "object",
      "properties": {
        "city":            { "type": "string" },
        "state":           { "type": "string" },
        "state_abbr":      { "type": "string", "maxLength": 3 },
        "zip":             { "type": "string" },
        "country":         { "type": "string" }
      }
    },
    "work_authorization":  { "type": "string", "examples": ["F-1 OPT", "H-1B", "GC", "USC"] },
    "requires_sponsorship":{ "type": "boolean" },
    "years_experience":    { "type": "integer", "minimum": 0 },
    "education": {
      "type": "object",
      "properties": {
        "level":           { "type": "string" },
        "university":      { "type": "string" },
        "major":           { "type": "string" },
        "graduation_year": { "type": "integer" },
        "gpa":             { "type": "number" }
      }
    },
    "salary": {
      "type": "object",
      "properties": {
        "min": { "type": "integer" },
        "max": { "type": "integer" },
        "currency": { "type": "string", "default": "USD" }
      }
    },
    "skills_summary":      { "type": "string" },
    "start_date":          { "type": "string", "examples": ["Immediately", "2025-07-01"] },
    "eeo": {
      "type": "object",
      "description": "Optional EEO fields; empty string means 'prefer not to say'.",
      "properties": {
        "gender":          { "type": "string" },
        "race":            { "type": "string" },
        "veteran_status":  { "type": "string" }
      }
    },
    "resume_updated_at":   { "type": "string", "format": "date-time" }
  }
}
```

The portal stores this in a `user_profile` table (per DECISIONS D10, per-user
tables are a later phase). The extension stores it under `chrome.storage.local`
key `profile` and merges from the portal on login.

---

## 3. Flows

### 3.1 Extension pulls profile + tailored resume PDF

```
Extension (content_script.js / options page)
  → GET /v1/me/profile         (Bearer token)
  ← 200 UserProfile JSON
  → stores to chrome.storage.local { profile: ... }

On "Resume" button click:
  → POST /v1/jobs/{id}/tailor  { jd, company, title }
  ← 200 application/pdf
  → chrome.runtime.sendMessage DOWNLOAD_PDF → background.js saves to Downloads
```

The portal replicates the `/tailor` pipeline for server-side rendering, which
lets resume generation work even without the local Node server running (Phase ≥6
of the portal roadmap).

### 3.2 "Applied" status flows back to a tracker

```
background.js logResult()  [today: POST localhost:4567/applications/log]
       ↓  replace with:
  → POST /v1/applications  { job_id, company, title, apply_url, status, applied_at }
  ← 201 { application_id }

Extension can also:
  → GET /v1/applications   ← list of user's submissions (deduplication source)
```

The portal's tracker replaces `resumes/applied_jobs.json` as the durable ledger,
accessible from any device.

### 3.3 Extension captures a job from a page the portal cannot scrape

Sites like LinkedIn and Naukri block server-side crawlers via robots.txt,
rate-limiting, or login walls (CLAUDE.md: "Respect the web: prefer public ATS
APIs; no scrapers for Naukri/LinkedIn or other ToS-forbidden portals").

The extension can capture job details **that the user already sees on screen**
in their own authenticated browser session. This is fundamentally different from
crawling: the user initiates the page load, the extension reads only the visible
rendered text that is already in the DOM, and sends a single record.

**ToS risk.** LinkedIn's ToS prohibits automated data collection. However,
courts (e.g. *hiQ v. LinkedIn*, 9th Cir.) have held that browser-assisted
scraping of user-initiated pages for personal use is legally distinct from
bulk automated crawling. To stay on solid ground:
- Capture is opt-in per click, never automatic.
- Only the fields visible to the user (title, company, location, JD text
  already rendered in the DOM) are sent — no profile data of other users.
- Never bulk-iterate job listings; capture one posting at a time.
- The portal must not re-publish LinkedIn/Naukri job data in its public feed.
- Users accept this risk in the portal's terms of service.

```
User browses linkedin.com/jobs/view/...
  Extension reads DOM via content_script.js (SITE_CONFIGS.linkedin selectors)
  → POST /v1/captures {
      source_url, title, company, location, jd_text,
      captured_at, source: "user_browser"
    }
  ← 201 { job_id }           (portal stores privately, never in public feed)
```

The `POST /v1/captures` endpoint stores the record in a private
`user_captured_jobs` table, not in `job_posting` (the public feed).

---

## 4. Auth: Extension ↔ Portal

### Comparison

| Criterion | OAuth2 PKCE | Device Code | Personal Access Token (PAT) |
|---|---|---|---|
| User experience | Pop-up/redirect; smooth | Visit URL + enter code; slightly awkward | Copy-paste from settings page |
| Token storage | `chrome.storage.local` (encrypted per-profile) | Same | Same |
| PKCE required | Yes — code_verifier prevents intercept | N/A | N/A |
| Short-lived access token | Yes (e.g. 1 h) | Yes | No — long-lived by default |
| Refresh token | Yes | Yes | N/A |
| Revocation | `/v1/auth/revoke` or provider UI | Same | Delete from portal settings |
| CSRF risk | Low — state param + PKCE | Low — code is single-use | Low — no redirect involved |
| CORS | Portal must allowlist `chrome-extension://` origin | Same | Same |

**Recommendation: PKCE flow** for first-party use (same developer owns both
repos). PKCE is the IETF-recommended grant for public clients with no server
secret (RFC 7636). Device code (RFC 8628) is better for TV/CLI contexts; it
adds an extra round-trip and is less natural for an extension pop-up.
PATs are acceptable as a developer escape hatch but should not be the default
because they are long-lived and hard to scope precisely.

**Token storage in `chrome.storage`.**
- Store `{ access_token, refresh_token, expires_at, scopes }` in
  `chrome.storage.local` (not `sync` — tokens should not roam to other devices).
- Never write tokens to `chrome.storage.session` (cleared on browser restart,
  forcing re-auth) unless you want that behaviour.
- On every API call, check `expires_at`; refresh silently if within 5 minutes.

**Scopes (proposed):**
- `profile:read` — `GET /v1/me/profile`
- `resume:read` — `GET /v1/jobs/{id}/resume.pdf`
- `applications:write` — `POST /v1/applications`
- `applications:read` — `GET /v1/applications`
- `captures:write` — `POST /v1/captures`

**CSRF / CORS.**
- PKCE `state` param protects the redirect callback.
- Portal API must set `Access-Control-Allow-Origin: chrome-extension://<id>`
  (extension ID is stable for sideloaded extensions; vary by build for
  published builds, or use a whitelist env var similar to `API_CORS_ORIGINS`).
- All state-mutating endpoints must verify the `Authorization` header is present
  (no cookie-based auth from the extension avoids CSRF entirely).

---

## 5. Minimal API Contract

Rate limit default: **60 req/min per token** (same Redis fixed-window as the
public API, `src/api/ratelimit.py`). PDF endpoints: 10 req/min.

| Method | Path | Request | Response | Rate |
|---|---|---|---|---|
| `GET` | `/v1/me/profile` | `Authorization: Bearer <token>` | `200 UserProfile` (§2 schema) | 60/min |
| `GET` | `/v1/jobs/{id}/resume.pdf` | `Authorization: Bearer <token>`; optional `?jd=<url-encoded>` to trigger server-side tailoring | `200 application/pdf`; header `X-JSeek-Match-Score: <0-100>` | 10/min |
| `POST` | `/v1/applications` | `{ job_id?, company, title, apply_url, status, applied_at }` | `201 { application_id, duplicate: bool }` | 60/min |
| `POST` | `/v1/captures` | `{ source_url, title, company, location?, jd_text, source }` | `201 { job_id }` | 30/min |
| `GET` | `/v1/applications` | `?page=<cursor>&limit=<1-50>` (default 20) | `200 { items: Application[], next_cursor }` | 60/min |

`Application` shape:
```json
{
  "application_id": "uuid",
  "job_id": "uuid | null",
  "company": "string",
  "title": "string",
  "apply_url": "string",
  "status": "submitted | needs_review | failed | duplicate",
  "applied_at": "ISO 8601"
}
```

All endpoints return `429 { error: "rate_limit_exceeded", retry_after: N }` on
breach and `401 { error: "unauthorized" }` on missing/expired token.

---

## 6. Duplication Audit and Shared Package Recommendation

| Feature | Portal (Python) | Extension (Node/JS) | Overlap |
|---|---|---|---|
| DOM scraping | `src/core/scrapers/*.py` (16 types: Workday, SmartRecruiters, DOM, NextData…) | `site_configs.js` + `content_script.js` `detectSite()` + universal heuristic | High — same platforms, different language. Portal runs headless; extension reads live DOM. |
| LLM routing | None today | `server.js callRelay()` → RelayFreeLLM 19-model cascade | Not in portal yet; may be added for server-side tailoring |
| LaTeX grafting | None today | `server.js graftPreamble()`, `extractLatex()`, `applySkillsLineTrimmer()` | Not in portal yet |
| Job aggregation | `src/workers/pipeline.py` → Postgres | `server.js GET /api/jobs` (Arbeitnow + Remotive + Jobicy) | Partial — portal has far more coverage; extension dashboard is a secondary view |
| Duplicate detection | None | `GET /applications/check` local, `appendLedger()` | Will overlap when portal tracker exists |

**Should a shared package be extracted?**

The scraper logic overlaps in intent but is architecturally distinct: the portal
runs server-side Python (Playwright, asyncpg) while the extension runs
client-side JavaScript in a browser context. A shared NPM + PyPI dual-publish
package would be heavy maintenance for what is essentially a list of CSS
selectors. **Recommendation: share data, not code.**

1. Extract `site_configs.js` selector maps to a **JSON file** (e.g.
   `site-configs.json`) versioned in this portal repo. The portal serves it at
   `GET /v1/site-configs` so the extension can pull updates without a release.
2. The **LaTeX grafting and LLM routing** live exclusively in JSeek's Node
   server for now. If the portal later needs server-side tailoring (§3.1), copy
   the three functions (`extractLatex`, `graftPreamble`, trimmer) into a small
   Python equivalent rather than bridging the language boundary with an RPC.
3. The portal's jobseek-fork scraper types (MIT-licensed `src/core/scrapers/`)
   are already separated from the extension's DOM scrapers by design; do not
   merge them.

---

## 7. Risks and Open Questions

| # | Risk / Question | Severity | Notes |
|---|---|---|---|
| R1 | ToS exposure on LinkedIn/Naukri captures | High | Mitigated by opt-in, single-record, user-session capture (§3.3). Portal must not republish data in public feed. Consult legal before shipping. |
| R2 | Extension ID stability | Medium | Chrome assigns a stable ID only for extensions published to the Web Store or sideloaded with a fixed key. A local dev build gets a random ID, breaking the CORS allowlist. Pin the extension key in `manifest.json` for dev and prod. |
| R3 | PII in portal DB | High | Profile schema includes email, phone, EEO. Needs encryption at rest, column-level access control, and compliance with D8 (pre-commit PII guard). Phase not scoped yet (D10). |
| R4 | `chrome.storage.local` token exposure | Medium | Accessible to any JS running in the extension's origin. Use short-lived tokens (≤1 h) + refresh; rotate on suspicious activity. |
| R5 | Server-side tailoring latency | Medium | pdflatex + LLM cascade can take 20–30 s. The portal's API timeout is 30 s (DECISIONS D12). Tailor should be async: `202 Accepted` + `GET /v1/jobs/{id}/resume.pdf?request_id=…` poll, or a WebSocket push. |
| R6 | Rate limit co-ordination | Low | Extension and portal share the same Redis rate limiter. Token-scoped limits (§5) must not starve the public API. |
| Q1 | Who owns `applied_jobs.json` migration? | — | Existing ledger entries should be imported on first login. |
| Q2 | Portal license (D7) | — | Must be decided before adding auth endpoints that handle PII. |
| Q3 | Should the extension dashboard (`GET /api/jobs`) be replaced by `GET /v1/jobs`? | — | Eliminates the Arbeitnow/Remotive/Jobicy third-party aggregation in the Node server in favour of the portal's 3,169-board feed. Likely yes, but scoped to a later phase. |
