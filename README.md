# myjobs

A continuously updated feed of tech jobs collected directly from company career pages, worldwide with an India focus. The index tracks approximately 3,000 career boards across major applicant tracking systems—including Greenhouse, Lever, Ashby, and Workday. It is public, read-only, and requires no sign-up or accounts. Candidates and developers can consume listings through a lightweight web interface or a JSON API.

## How it works

```
CSV registry ──► sync.py ──► Redis queues ──► Worker (monitors/scrapers) ──► Postgres ──► FastAPI ──► Next.js
(companies.csv,              (priority &      (HTTP & browser pipelines;       (enriched  (/api/v1)  (web/)
 boards.csv)                  rate limits)     GeoNames & salary parsing)       postings)
```

- **Per-domain rate limits:** Crawl tasks are throttled in Redis per domain (or shared across ATS endpoints) with exponential backoff and jitter, avoiding unnecessary load on company servers.
- **SSRF guard:** An HTTP transport guard resolves DNS and checks IP addresses against private networks, link-local addresses, and cloud metadata services on every request and redirect hop.
- **robots.txt compliance:** Site-reading and sitemap monitors check and honour robots.txt directives before fetching, while direct API monitors query official candidate endpoints.
- **GeoNames locations:** Location strings are resolved against GeoNames database entries, supporting hierarchical country, region, and macro-region filtering (such as India, APAC, or EU) without substring collision issues.
- **INR/LPA salary parsing:** Job descriptions are parsed for Indian compensation structures (LPA, lakh, crore, monthly CTC) alongside international currencies to extract structured numeric bounds.
- **Discovery pipeline:** Candidate domains pass through careers page detection, ATS fingerprinting, robots verification, and parse checks into a review queue before promotion to the active registry.

## Quick start

The environment template is `.env.example`. Copy it to `.env` before running services.

### Setup

```bash
cp .env.example .env
pip install -e ".[dev]"
python -m playwright install chromium
docker compose up -d
alembic upgrade head
python scripts/load_geonames.py
python scripts/populate_taxonomy.py
```

### Running services

Start the continuous crawl worker:

```bash
myjobs worker
```

Start the API server (available at `http://127.0.0.1:8080`, docs at `/api/docs`):

```bash
myjobs serve
```

Start the web interface:

```bash
cd web && npm install && API_ORIGIN=http://127.0.0.1:8080 npm run dev
```

## API

The backend exposes a public, unauthenticated JSON API with rate limiting and keyset pagination.

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/jobs` | GET | List jobs with filtering and keyset pagination |
| `/api/v1/jobs/{job_id}` | GET | Job details with sanitized HTML description |
| `/api/v1/companies` | GET | List tracked companies with active job counts |
| `/api/v1/locations` | GET | Search GeoNames locations by prefix or keyword |
| `/api/v1/stats` | GET | Feed freshness and posting statistics |
| `/api/v1/coverage` | GET | Crawler health and coverage breakdown by ATS and region |
| `/healthz` | GET | Health check endpoint |

### `/api/v1/jobs` query parameters

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Free-text search matching title or company name (max 100 characters) |
| `country` | string | ISO-3166 alpha-2 country code (`IN`, `US`) or macro region (`EU`, `APAC`) |
| `location` | integer | GeoNames ID for a specific city, administrative area, or country |
| `company` | string | Filter by company slug |
| `work_mode` | string | `remote`, `hybrid`, or `onsite` |
| `since` | string | Relative timeframe (`24h`, `7d`) or ISO-8601 timestamp |
| `seniority` | string | Seniority level filter |
| `occupation` | string | Occupation taxonomy filter |
| `cursor` | string | Keyset pagination token |
| `limit` | integer | Results per page (1 to 100, default 50) |

### Example request

```bash
curl "http://127.0.0.1:8080/api/v1/jobs?country=IN&since=24h"
```

## Respectful crawling

The crawler is designed to be considerate of company infrastructure:

- **Public ATS APIs preferred:** Roughly 86% of tracked boards use official candidate-facing endpoints (Greenhouse, Lever, Ashby, Workday CXS, and others) rather than HTML page scraping.
- **robots.txt honoured:** Any monitor reading HTML or sitemaps validates access permissions against the site's robots.txt rules before issuing requests.
- **No scraping of restricted portals:** The project explicitly does not scrape job aggregators or professional networks whose terms of service prohibit automated scraping (such as LinkedIn, Naukri, or Indeed).
- **Per-domain rate limits:** Crawl tasks are throttled per hostname in Redis to prevent burst traffic on destination hosts.

## Status and roadmap

The project is currently focused on the public feed. See [docs/REVAMP_PLAN.md](docs/REVAMP_PLAN.md) for the roadmap and [docs/DECISIONS.md](docs/DECISIONS.md) for architecture decisions.

Per-user profiles, scoring, and anti-fabrication resume tailoring come later as separate phases.

## Credits and licence

- Crawler core, queue design, and monitor implementations are derived from [colophon-group/jobseek](https://github.com/colophon-group/jobseek) (MIT License, Copyright 2025 Viktor Shcherbakov).
- Location reference data is sourced from [GeoNames](https://www.geonames.org/) under the Creative Commons Attribution 4.0 License.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full attribution and third-party license texts.

The project's own licence is not yet chosen.
