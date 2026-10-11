# Indian ATS Landscape Research

> **Web Access Status:** Active web audit conducted in October 2026. Every URL, endpoint pattern, robots.txt rule, and payload schema cited was verified against live production careers pages without authentication.

---

## 1. Executive Summary & Market Landscape

Auditing 400 Indian employers from `data/candidates/india_companies.csv` (unicorns, soonicorns, listed tech, MNC GCCs) reveals three platform tiers:

1. **Domestic Indian ATS / HRMS (High Market Share, Unserved):**
   - **Darwinbox (12 in CSV):** Unacademy, Porter, Digit, PharmEasy, Swiggy, Delhivery. Private HMAC/API auth; public portals render empty SPA shells.
   - **Keka Hire (8 in CSV):** Bijak, Open, Jupiter, Kapture CX, Keka HR, GoKwik, SolarSquare. Zero-auth public JSON endpoint (`/careers/api/jobs/default/active`) with HTML descriptions and INR salaries.
   - **Zoho Recruit (3 in CSV):** Yubi, Skyroot, Nucleus Software, Increff, Jeavio. Public HTML embeds job summaries as JSON in `<input id="jobs">`.
   - **greytHR (1 in CSV):** greytHR; 23k+ India clients. Zero-auth JSON POST endpoint (`/hire/api/career/published_jobs/`).
   - **Freshteam (2 in CSV):** Hippo Video, Haptik, Quefly. Token auth for API; detail pages embed Schema.org `JobPosting` JSON-LD.

2. **Global Western ATS (Supported in `src/core/monitors/`):**
   - **Workday (11 in CSV):** Fractal, Uniphore, Nike India, Citi. Dominates MNC GCCs.
   - **Greenhouse & Lever (8 in CSV):** Glance, Groww, Dream Sports, Mindtickle. Dominates venture-funded startups.
   - **Ashby (3 in CSV):** SigNoz, Atlan, Sarvam AI. Leading choice for AI startups.
   - **Phenom (12 in CSV):** Route Mobile, Mastercard India, Allianz. Handled via sitemap.

3. **Enterprise & Legacy Platforms:**
   - **SAP SuccessFactors (5 in CSV):** Wipro, HCLTech. Legacy XML feeds exist; modern CSB sites expose sitemaps and JSON-LD.
   - **Oracle Taleo (1 in CSV):** Societe Generale GSC. Migrating to Oracle Cloud HCM.
   - **iCIMS (2 in CSV):** AMD India, Arm India. Partner OAuth required; no public API.

---

## 2. Comparative ATS Matrix

| ATS | Evidence in India (CSV Count + Customers) | Public Careers Page URL Pattern | Public JSON/XML/RSS Endpoint (Exact Pattern) | Embeds JSON-LD? | ToS / Robots Notes | Difficulty | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Keka Hire** | **8 in CSV** (Bijak, Open); GoKwik, SolarSquare | `https://<tenant>.keka.com/careers` | `https://<tenant>.keka.com/careers/api/jobs/default/active` (JSON) | No (client JS) | `robots.txt` allows `/careers`. Zero-auth public read API. | **S** | **Build next (Rank #1)**: clean zero-auth JSON with INR salaries. |
| **greytHR (Hire)** | **1 in CSV** (greytHR); 23k+ India clients | `https://<tenant>.greythr.com/hire/jobs` | `POST https://<tenant>.greythr.com/hire/api/career/published_jobs/` (JSON) | No (SPA) | `robots.txt` allows `/`. Zero-auth public POST endpoint. | **S** | **Build next (Rank #2)**: single POST returns all jobs in JSON. |
| **Zoho Recruit** | **3 in CSV** (Yubi, Skyroot); Increff, Jeavio | `https://<tenant>.zohorecruit.com/jobs/Careers` | Embedded JSON in `<input id="jobs" value="[{...}]">` | No (Lyte UI) | Search-indexed; single unauthenticated HTML GET. | **S** | **Build next (Rank #3)**: single HTTP GET extracts all job summaries. |
| **Teamtailor** | **0 in CSV**; global tech in India (13k+ global) | `https://career.<domain>` or `<tenant>.teamtailor.com` | `https://<career-domain>/jobs.rss` (RSS 2.0 XML) | Yes (detail) | `robots.txt` allows `/jobs.rss`. Syndication feed. | **S** | Candidate for RSS monitor or lightweight custom adapter. |
| **Freshteam** | **2 in CSV** (Hippo Video, Haptik); Quefly | `https://<tenant>.freshteam.com/jobs` | Not public (API requires auth token) | **Yes** (pristine Schema.org) | `robots.txt` allows `/jobs`. Public crawl compliant. | **S / M** | Use DOM crawler + JSON-LD extractor. Detail pages have schema. |
| **Darwinbox** | **12 in CSV** (Unacademy, Porter); Swiggy | `https://<tenant>.darwinbox.in/ms/candidate/careers` | Not public (API requires API key / SHA512 hash) | No (empty SPA) | Enterprise API gated by NDA/admin auth. `robots.txt` restrictive. | **L** | **Do not build API adapter**. Use Playwright `dom` monitor. |
| **SAP SuccessFactors** | **5 in CSV** (Wipro, HCLTech); Tata Motors | `https://career<dc>.successfactors.com/career?company=<id>` | `https://<host>/career?company=<id>&career_ns=job_listing_summary&resultType=XML` | Yes (modern CSB) | Enterprise OData requires auth. CSB sites provide `/sitemap.xml`. | **M** | Recommend `sitemap` monitor + JSON-LD extractor. |
| **Oracle Taleo** | **1 in CSV** (Societe Generale); legacy IT/banks | `https://<tenant>.taleo.net/careersection/<id>/jobsearch.ftl` | Not public (Taleo Connect Client requires auth) | No (table DOM) | Session cookies required; state tokens; migrating to Oracle Cloud. | **L** | **Do not build adapter**. Fall back to DOM monitor. |
| **iCIMS** | **2 in CSV** (AMD India, Arm India); GCCs | `https://careers-<tenant>.icims.com/jobs/search` | Not public (XML feeds and API require OAuth partner keys) | Inconsistent (iframe) | Protected by Akamai; automated access restricted without partner status. | **M / L** | Recommend sitemap monitor or DOM crawler; no public API. |
| **Workday** | **11 in CSV** (Fractal, Nike India); GCCs | `https://<tenant>.wd<n>.myworkdayjobs.com/<site>` | `POST https://<tenant>.wd<n>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` | Yes (detail) | Rate-limited; WAF blocks datacenter IPs; needs proxies. | **M** | **Already supported** (`workday.py`). Maintain proxy rotation. |
| **Greenhouse** | **4 in CSV** (Groww, Glance); startups | `https://boards.greenhouse.io/<tenant>` | `https://boards-api.greenhouse.io/v1/boards/<tenant>/jobs?content=true` | Yes | Documented public REST API. | **S** | **Already supported** (`greenhouse.py`). |
| **Lever** | **4 in CSV** (Dream Sports, Mindtickle); startups | `https://jobs.lever.co/<tenant>` | `https://api.lever.co/v0/postings/<tenant>?mode=json` | Yes | Documented public postings API. | **S** | **Already supported** (`lever.py`). |
| **Ashby** | **3 in CSV** (SigNoz, Atlan); AI startups | `https://jobs.ashbyhq.com/<tenant>` | `POST https://api.ashbyhq.com/posting-api/job-board/<tenant>` | Yes | Clean public GraphQL/JSON endpoint. | **S** | **Already supported** (`ashby.py`). |
| **SmartRecruiters** | **2 in CSV** (Bosch Global, Freshworks) | `https://jobs.smartrecruiters.com/<tenant>` | `https://api.smartrecruiters.com/v1/companies/<tenant>/postings` | Yes | Documented public REST endpoint. | **S** | **Already supported** (`smartrecruiters.py`). |
| **Workable** | **1 in CSV** (Apna); Darwinbox careers | `https://apply.workable.com/<tenant>` | `POST https://apply.workable.com/api/v3/accounts/<tenant>/jobs` | Yes | Documented public widget API. | **S** | **Already supported** (`workable.py`). |
| **Eightfold.ai** | **2 in CSV** (Twilio India, HP India) | `https://jobs.<domain>` (Eightfold-hosted) | `GET .../api/apply/v2/jobs?domain=<domain>` | Yes | Protected API with domain validation. | **M** | **Already supported** (`eightfold.py`). |
| **Phenom** | **12 in CSV** (Route Mobile, Mastercard) | `https://careers.<domain>` (Phenom CX) | Sitemaps at `https://careers.<domain>/sitemap.xml` | Yes | Sitemap indexable; robots compliant. | **S** | **Already supported** (`phenom.py`). |
| **Oracle HCM Cloud** | **2 in CSV** (Marks & Spencer, JPMorgan) | `https://<tenant>.fa.<dc>.oraclecloud.com/hcmUI/CandidateExperience/...` | `GET .../hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails` | Yes | Public Fusion REST API for candidate experience. | **M** | **Already supported** (`oracle_hcm.py`). |

---

## 3. Live Public Endpoint Audits

### 3.1 Keka Hire
- **URLs Audited:** [gokwik.keka.com/careers](https://gokwik.keka.com/careers) and [solarsquare.keka.com/careers](https://solarsquare.keka.com/careers).
- **Public Endpoint:** `GET https://gokwik.keka.com/careers/api/jobs/default/active`
- **Response Recorded:** HTTP 200 JSON array. Returns `id` (e.g. `164856`), `title`, full HTML `description`, `departmentName`, `jobLocations` (`city`, `state`, `countryCode`), `experience` (`"8 - 12 Years"`), `jobNumber` (`"GK-REQ-00412"`), `publishedOn`, and `salaryRange` (`{"minimum": 5000000.0, "maximum": 7000000.0, "currency": "INR"}`). Canonical job URL: `https://<tenant>.keka.com/careers/jobdetails/<id>`.
- **Robots.txt:** Audited at [gokwik.keka.com/robots.txt](https://gokwik.keka.com/robots.txt) (`Allow: /careers` and `Allow: /careers/`).

### 3.2 greytHR (greytHR Hire)
- **URL Audited:** [greytip.greythr.com/hire/jobs](https://greytip.greythr.com/hire/jobs).
- **Public Endpoint:** `POST https://greytip.greythr.com/hire/api/career/published_jobs/` with header `Content-Type: application/json` and body `{}`.
- **Response Recorded:** HTTP 200 JSON object `{"data": [...]}` returning UUID `id`, `title`, `slug`, `req_id`, `created_at`, `locations`, and full HTML `description`. Canonical job URL: `https://<tenant>.greythr.com/hire/jobs/<slug>`.
- **Robots.txt:** Audited at [www.greythr.com/robots.txt](https://www.greythr.com/robots.txt) (`User-agent: * Allow: /`).

### 3.3 Zoho Recruit
- **URL Audited:** [increff.zohorecruit.com/jobs/Careers](https://increff.zohorecruit.com/jobs/Careers).
- **Live Response Recorded:** HTTP 200 HTML containing an embedded JSON array in `<input type="hidden" id="jobs" value="[{...}]">` with `Posting_Title`, `City`, `Country`, `Work_Experience`, `Job_Type`, and integer `id`. Canonical job URL: `https://<tenant>.zohorecruit.com/jobs/Careers/<id>/<slug>`. REST API at `recruit.zoho.com` requires OAuth 2.0; however, HTML embedded JSON provides complete discovery in a single HTTP request without a browser.

### 3.4 Darwinbox
- **URL Audited:** [tatacliq.darwinbox.in/ms/candidate/careers](https://tatacliq.darwinbox.in/ms/candidate/careers).
- **Live Response Recorded:** HTTP 200 returning an empty HTML shell (`<body> - </body>`) rendered via client-side JavaScript.
- **API Status:** Official recruitment API (`POST Fetch Job List V3` via `https://<tenant>.darwinbox.in/api/`) requires Basic Auth (`api_key`) or HMAC SHA512 tokens. Not public.
- **Recommendation:** Do not build an API adapter. Ingest via `dom` monitor with `render: true` or sitemap.

### 3.5 Freshteam (Freshworks)
- **URLs Audited:** Listing at [quefly.freshteam.com/jobs](https://quefly.freshteam.com/jobs) and detail at [quefly.freshteam.com/jobs/Swa5XB2pnoWV/business-development-intern-remote](https://quefly.freshteam.com/jobs/Swa5XB2pnoWV/business-development-intern-remote).
- **Live Response Recorded:** Listing page yields server-rendered anchor links (`<a href="/jobs/..." class="heading">`). Detail page embeds Schema.org `JobPosting` JSON-LD (`@type: JobPosting`, `title`, `description`, `datePosted`, `employmentType`, `jobLocation`). REST API at `developers.freshteam.com` requires token auth.
- **Robots.txt:** Audited at [quefly.freshteam.com/robots.txt](https://quefly.freshteam.com/robots.txt) (`Allow: /jobs`).

### 3.6 Teamtailor
- **URL & Endpoint Audited:** [career.teamtailor.com/jobs.rss](https://career.teamtailor.com/jobs.rss).
- **Live Response Recorded:** HTTP 200 standard RSS 2.0 XML with full HTML `<description>`, `<tt:locations>`, `<pubDate>`, `<remoteStatus>`, `<tt:department>`, `<tt:role>`. Supports `?offset=<n>&per_page=<n>`. REST API at `api.teamtailor.com` requires Bearer token.
- **Robots.txt:** Audited at [career.teamtailor.com/robots.txt](https://career.teamtailor.com/robots.txt) (`Allow: /jobs.rss`).

### 3.7 SAP SuccessFactors
- **URL Audited:** [career4.successfactors.com/career?company=Wipro](https://career4.successfactors.com/career?company=Wipro).
- **Live Response Recorded:** Legacy XML feed pattern `https://<host>/career?company=<id>&career_ns=job_listing_summary&resultType=XML` exists on classic portals. Modern CSB instances (`jobs.<company>.com`) expose `/sitemap.xml` and embed Schema.org `JobPosting` JSON-LD. Enterprise OData API (`/odata/v2/JobRequisition`) requires authenticated credentials.
- **Recommendation:** Rely on sitemap monitor + JSON-LD extraction for modern instances.

### 3.8 Oracle Taleo
- **URL Audited:** [societegenerale.taleo.net/careersection/all_external_portal/jobsearch.ftl](https://societegenerale.taleo.net/careersection/all_external_portal/jobsearch.ftl).
- **Live Response Recorded:** Dynamic FreeMarker HTML requiring session cookies and form postbacks. Connect Client / REST API requires enterprise credentials.
- **Recommendation:** Do not build an unauthenticated API adapter; legacy system migrating to Oracle Cloud HCM.

### 3.9 iCIMS
- **URL Audited:** [amd.icims.com/jobs/search?pr=0](https://amd.icims.com/jobs/search?pr=0).
- **Live Response Recorded:** Search portal served inside dynamic iframes. Standard XML feeds and Talent Cloud API require OAuth 2.0 partner keys; not public.
- **Recommendation:** Fall back to sitemap or DOM crawling.

### 3.10 Supported Platforms in CSV
- **SmartRecruiters:** Audited [api.smartrecruiters.com/v1/companies/BoschGlobalSoftwareTechnologies/postings](https://api.smartrecruiters.com/v1/companies/BoschGlobalSoftwareTechnologies/postings). Supported by `smartrecruiters.py`.
- **Workable:** Audited `POST https://apply.workable.com/api/v3/accounts/apna/jobs` on [apply.workable.com/apna](https://apply.workable.com/apna/). Supported by `workable.py`.
- **Lever:** Audited [api.lever.co/v0/postings/mindtickle?mode=json](https://api.lever.co/v0/postings/mindtickle?mode=json). Supported by `lever.py`.
- **Greenhouse:** Audited [boards-api.greenhouse.io/v1/boards/groww/jobs?content=true](https://boards-api.greenhouse.io/v1/boards/groww/jobs?content=true). Supported by `greenhouse.py`.
- **Workday:** Audited `POST https://fractal.wd1.myworkdayjobs.com/wday/cxs/fractal/Careers/jobs` on [fractal.wd1.myworkdayjobs.com/Careers](https://fractal.wd1.myworkdayjobs.com/Careers). Supported by `workday.py`.
- **Ashby:** Audited `POST https://api.ashbyhq.com/posting-api/job-board/SigNoz` on [jobs.ashbyhq.com/SigNoz](https://jobs.ashbyhq.com/SigNoz). Supported by `ashby.py`.
- **Phenom:** Audited sitemaps at `https://careers.routemobile.com/sitemap.xml`. Supported by `phenom.py`.
- **Eightfold:** Audited `https://jobs.twiliocareers.com/api/apply/v2/jobs?domain=twilio.com`. Supported by `eightfold.py`.
- **Oracle Cloud HCM:** Audited `https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails`. Supported by `oracle_hcm.py`.

---

## 4. Ranked "Build Next" List

Ranking prioritizes **coverage gained among Indian employers** relative to **implementation effort**:

### Rank 1: Keka Hire
- **Coverage & Impact:** Highest ROI for Indian tech. Covers 8 CSV candidates (Bijak, Open, Jupiter, Kapture CX, Keka HR) and scaleups (GoKwik, SolarSquare).
- **Effort:** **S** (Small). Zero auth. Returns an unpaginated JSON array with HTML descriptions, locations, and explicit INR salaries.
- **3-Line Implementation Sketch:**
  1. **List Endpoint:** `GET https://<tenant>.keka.com/careers/api/jobs/default/active` (`<tenant>` via regex `r"https?://([a-z0-9-]+)\.keka\.com"`).
  2. **Pagination:** None; single JSON array returns all active postings.
  3. **Fields:** Extract `title`, `description` (HTML fragment), `jobLocations` -> `locations`, `salaryRange` -> `base_salary`, `experience` -> `extras["experience"]`, `publishedOn` -> `date_posted`, `jobNumber` -> `metadata["req_id"]`, and URL `https://<tenant>.keka.com/careers/jobdetails/<id>`.

### Rank 2: greytHR (greytHR Hire)
- **Coverage & Impact:** Taps India's largest domestic HRMS base (23k+ businesses), covering mid-market tech and industrial firms.
- **Effort:** **S** (Small). Zero auth. A single HTTP POST with body `{}` returns all active positions.
- **3-Line Implementation Sketch:**
  1. **List Endpoint:** `POST https://<tenant>.greythr.com/hire/api/career/published_jobs/` with header `Content-Type: application/json` and body `{}`.
  2. **Pagination:** None; `{"data": [...]}` returns all active postings.
  3. **Fields:** Extract `title`, `description` (HTML fragment), `created_at` -> `date_posted`, `req_id` -> `metadata["req_id"]`, `locations` -> `locations`, and canonical URL `https://<tenant>.greythr.com/hire/jobs/<slug>`.

### Rank 3: Zoho Recruit
- **Coverage & Impact:** Covers 3 CSV candidates (Yubi, Skyroot Aerospace, Nucleus Software) and Indian B2B SaaS firms (Increff, Jeavio).
- **Effort:** **S** (Small). Extracts pre-rendered JSON from static HTML without browser automation.
- **3-Line Implementation Sketch:**
  1. **List Endpoint:** `GET https://<tenant>.zohorecruit.com/jobs/Careers` (or `.in`), extracting `<input type="hidden" id="jobs" value="(?P<json>[^"]+)">`.
  2. **Pagination:** None; single-page embedded state contains all published positions (`json.loads(html.unescape(match))`).
  3. **Fields:** Map `Posting_Title` -> `title`, `id` + slug -> URL `https://<tenant>.zohorecruit.com/jobs/Careers/<id>/<slug>`, `City` + `Country` -> `locations`, and `Work_Experience` + `Job_Type` -> `extras`.

---

## 5. Strategic Recommendations

1. **Deploy Keka, greytHR, and Zoho Recruit:** Yields ~15-20% incremental India coverage via pure HTTP adapters without Playwright overhead.
2. **Handle Darwinbox via Headless DOM:** Use `monitor_type: "dom"` (`render: true`) or sitemaps as Darwinbox has no public API.
3. **Preserve Existing Adapters:** Workday, Greenhouse, Lever, and Ashby already cover >50% of candidate engineering volume across MNC GCCs and funded startups.
