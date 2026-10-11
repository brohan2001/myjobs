# Infrastructure Proposal: Production Deployment for a Solo Developer

*Status: Proposal only. Target: Solo developer in India on a lean budget.*  
*Pricing notice: All prices are estimates as of knowledge cutoff (mid-2024 to early 2026); verify before buying. FX rates: $1 ≈ ₹83–₹86, €1 ≈ ₹90–₹94. Local taxes (e.g., 18% Indian GST) may apply.*

---

## 1. Hosting Options Comparison

### 1.1 Summary Comparison Table

| Component | Option | Est. Cost (₹/mo) | Pros | Cons / Caveats |
|---|---|---|---|---|
| **Database** | **Self-hosted VPS (Postgres 16)** | **₹0 extra** (co-located) or **₹380–₹500** | Full `pg_trgm` & GIN support; NVMe storage; zero storage markup on 2–5 GB data. | Requires self-managed backups (`pg_dump`) and OS patching. |
| | **Supabase** | **₹2,100–₹2,500** ($25/mo Pro) | Managed backups, native Auth, RLS UI, connection pooler. | Free tier (500 MB) is too small for ~400k postings and pauses on idle. |
| | **Neon** | **₹1,600–₹2,200** ($19/mo Launch + usage) | Instant branching, excellent DX. | Free tier capped at 0.5 GB. 24/7 continuous crawling negates scale-to-zero. |
| | **Railway Postgres** | **₹1,250–₹2,500** ($15–$30/mo usage) | One-click setup, unified dashboard. | RAM ($10/GB) and CPU ($20/vCPU) usage fees mount under continuous writes. |
| **Worker** | **Hetzner CPX21 VPS** | **₹700–₹850** (~€7.50–€8.50/mo) | 3 vCPU AMD, 4 GB RAM, 80 GB NVMe, 20 TB traffic. Handles 40 async workers + Playwright. | EU datacenters (latency negligible for scrapers; API uses edge CDN). |
| | **Oracle Cloud Free Tier (ARM)** | **₹0** (Always Free) | 4 OCPU Ampere A1, 24 GB RAM, 200 GB disk. Mumbai/Hyderabad regions exist. | Strict sign-up validation; sporadic Indian capacity; idle reclamation risk. |
| | **DO / Linode (Bangalore/Mumbai)** | **₹2,000–₹2,400** ($24/mo, 2 vCPU / 4 GB) | Indian datacenter (low latency), reliable networking. | ~3× the cost of Hetzner for comparable specs. |
| | **Fly.io** | **₹1,250–₹2,100** ($15–$25/mo) | Global microVMs, container-native. | 24/7 compute accumulates; Playwright RAM spikes (~1 GB) risk OOMs on 2 GB VMs. |
| | **Railway Worker** | **₹2,900–₹3,800** ($35–$45/mo usage) | Git-push deploys, zero server config. | Expensive for continuous background daemons with persistent load. |
| | **Render** | **₹2,100–₹2,500** ($25/mo Standard) | Managed platform, built-in TLS. | 512 MB Starter ($7) OOMs on Chromium; 2 GB plan ($25) is too costly for solo dev. |
| | **GitHub Actions Cron** | **Not recommended** | Free minutes allowance. | **Unsuitable for always-on crawlers** (see §1.2). |
| **Frontend** | **Cloudflare Pages** | **₹0** (Free tier) | Unlimited bandwidth, 20+ edge locations in India, Anycast CDN, DDoS defense. | Requires static export or adapter (`@cloudflare/next-on-pages` / OpenNext). |
| | **Vercel** | **₹0** (Hobby tier) | Native Next.js App Router support, server actions, Mumbai edge. | Hobby tier restricts commercial use; bandwidth overages can become expensive. |
| **API** | **Co-located with Worker (on VPS)** | **₹0 extra** | Sub-millisecond loopback queries to Postgres/Redis; single host; zero extra bill. | Shared CPU/RAM during Playwright runs (handled via process nice/cgroups). |
| | **Separate Container (PaaS)** | **₹450–₹1,250** ($5–$15/mo) | Isolated failure domain from worker. | Cross-region network latency (100–150 ms) to DB hurts feed latency; extra cost. |
| **Redis** | **Self-hosted Redis 7 (on VPS)** | **₹0 extra** | Uses <100 MB RAM; sub-millisecond Lua script evaluation; no command quotas. | Needs local process or container supervision (systemd / Docker). |
| | **Upstash (Serverless Redis)** | **₹400–₹1,500** ($5–$18/mo) | Zero ops, web console. | Free tier (10k cmds/day) exceeded in minutes by 40 workers checking leases (500k+ ops/day). |

### 1.2 Why GitHub Actions Cron is Unsuitable for an Always-On Crawler

1. **Daemon Architecture Mismatch:** `myjobs worker` is a continuous pipeline with in-memory/Redis leases (`inflight_lease_ttl_seconds`), token-bucket domain throttles, and reaper loops. Ephemeral cron runners discard rate-limiting state on exit, risking aggressive request bursts on target ATS domains upon each restart.
2. **Cold Start & Overhead:** Each run spins up a fresh VM. Installing Python dependencies, Playwright, and Chromium binaries takes 2–4 minutes before any crawling begins.
3. **Execution Limits & Jitter:** Actions caps workflows at 6 hours, and GitHub cron triggers suffer from unpredictable delays (often 30–60 minutes late during peak hours).
4. **ToS Violations:** GitHub's Acceptable Use Policy prohibits using Actions as a continuous background scraping daemon.

---

## 2. Target Multi-Tenant Schema Sketch

When transitioning from the public feed to user accounts, per-user scoring, and resume tailoring (DECISIONS D10), the database must enforce tenant isolation while sharing public job and company catalogs.

### 2.1 Target Schema Entities

- **`app_user` (Tenants):** `id UUID PK`, `email CITEXT UNIQUE NOT NULL`, `role TEXT NOT NULL DEFAULT 'user'`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`.
- **`profile` (Master Profile):** `user_id UUID PK FK->app_user(id)`, `version INT NOT NULL DEFAULT 1`, `raw_profile JSONB NOT NULL DEFAULT '{}'` (identity, education, experience, verified skills with `source_ref`), `updated_at TIMESTAMPTZ`.
- **`resume_file` (Sensitive Resumes):** `id UUID PK`, `user_id UUID NOT NULL FK->app_user(id)`, `file_name TEXT`, `file_type TEXT` ('pdf'|'docx'|'tex'), `storage_uri TEXT` ('r2://resumes/{user_id}/{id}.enc'), `enc_blob_key_ref TEXT` (envelope encryption key reference), `parsed_data JSONB`, `created_at TIMESTAMPTZ`.
- **`preference` (User Preferences):** `user_id UUID PK FK->app_user(id)`, `target_roles TEXT[]`, `location_ids INT[]`, `work_modes TEXT[]`, `min_salary_inr INT`, `experience_band TEXT`, `include_keywords TEXT[]`, `exclude_keywords TEXT[]`, `scoring_weights JSONB`, `updated_at TIMESTAMPTZ`.
- **`company` (Catalog, existing):** `id UUID PK`, `slug TEXT UNIQUE`, `name TEXT`, `website TEXT`, `logo TEXT`, `industry SMALLINT`, `extras JSONB`.
- **`job_board` / `sources` (Catalog, existing):** `id UUID PK`, `company_id UUID FK`, `board_url TEXT UNIQUE`, `monitor_type TEXT`, `check_interval_minutes INT`, `consecutive_failures INT`, `board_status TEXT`.
- **`job_posting` (Catalog, existing + deduplication):** `id UUID PK`, `company_id UUID FK`, `board_id UUID FK`, `titles TEXT[]`, `location_ids INT[]`, `employment_type TEXT`, `salary_min INT`, `salary_max INT`, `is_active BOOL`, `first_seen_at TIMESTAMPTZ`, `canonical_dedupe_key TEXT UNIQUE` (hash of normalized `company_id || lower(title) || sorted_location_ids`).
- **`user_job_score` (Per-User Scores, decoupled per D10):** `user_id UUID FK->app_user(id)`, `posting_id UUID FK->job_posting(id)`, `total_score SMALLINT`, `skill_score SMALLINT`, `role_score SMALLINT`, `recency_score SMALLINT`, `company_score SMALLINT`, `breakdown JSONB`, `calculated_at TIMESTAMPTZ`, `PRIMARY KEY (user_id, posting_id)`.
- **`application` (Tracker & Tailored Resumes):** `id UUID PK`, `user_id UUID NOT NULL FK->app_user(id)`, `posting_id UUID NOT NULL FK->job_posting(id)`, `status TEXT` ('saved'|'tailoring'|'applied'|'interview'|'rejected'), `tailored_resume_id UUID FK->resume_file(id)`, `notes TEXT`, `applied_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`, `UNIQUE (user_id, posting_id)`.
- **`pipeline_run` (Audit & Observability):** `id UUID PK`, `run_type TEXT` ('crawl'|'sync'|'scoring'|'expiry'), `started_at TIMESTAMPTZ`, `completed_at TIMESTAMPTZ`, `status TEXT`, `stats JSONB`.

### 2.2 Postgres Row Level Security (RLS) Implementation

Tenant isolation is enforced directly in Postgres:
1. **Tenant Context Binding:** Authenticated API requests execute:
   `SET LOCAL app.current_user_id = '<user_uuid>';`
2. **Tenant Table Isolation:**
   `ALTER TABLE <tbl> ENABLE ROW LEVEL SECURITY;` on `profile`, `resume_file`, `preference`, `user_job_score`, and `application`.  
   Policy: `USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID);`
3. **Public Catalog Access:** Shared tables (`company`, `job_board`, `job_posting`, `location`, `descriptions`) use a permissive read policy: `FOR SELECT USING (true)`.
4. **Crawler Bypass:** The worker connects using role `crawler_role` with `BYPASSRLS` privileges, writing jobs without tenant restrictions.

### 2.3 Migration Path from Current Schema (Alembic)

The current migration head is `0009_public_feed.py`. The non-breaking upgrade sequence:
- **Migration `0010_user_and_tenant_core.py`:** Create `app_user`, `profile`, `resume_file`, `preference`. Add `canonical_dedupe_key` column and unique partial index to `job_posting`.
- **Migration `0011_user_scoring_applications.py`:** Create `user_job_score`, `application`, and `pipeline_run` tables with indexing (`user_id, total_score DESC`).
- **Migration `0012_enable_rls.py`:** Enable RLS on user-specific tables, define security policies, and create `app_user_role` and `crawler_role` database roles.
- **Impact:** Zero downtime or schema disruption for existing crawler or public feed endpoints.

---

## 3. Continuous Updates & Freshness

### 3.1 Board Crawl Cadence by Tier (~3,100 Boards)

| Tier | Characteristics | Cadence | Concurrency & Worker Mode |
|---|---|---|---|
| **Tier 1 (Hot Companies)** | FAANG, top Indian unicorns, high-turnover ATS (Greenhouse, Lever). | **Every 15–30 min** | Async HTTP pipeline (`discovery_concurrency=40`). Fast JSON endpoints. |
| **Tier 2 (Standard Tech)** | Mid-tier tech companies, standard ATS portals (Workday, Taleo). | **Every 1–2 hours** | Async HTTP pipeline with domain rate limiting. |
| **Tier 3 (Long-Tail)** | Infrequently updated boards, corporate sites, small consultancies. | **Every 6–12 hours** | Off-peak scheduled sweeps to conserve bandwidth. |
| **Browser Boards (~120 boards)** | Complex pages requiring Playwright Chromium rendering. | **Every 12–24 hours** (nightly) | Dedicated browser queue capped at 2 concurrent Chromium instances (~1 GB RAM ceiling). |

### 3.2 Politeness Architecture (DECISIONS D6 & D14)
- **Token-Bucket Throttling:** Enforced per root domain via Redis Lua scripts (`throttle_delay_default = 2.0s`, `throttle_delay_ats = 0.5s`). Host concurrency is strictly capped at 1 active request.
- **Honest User-Agent:** Header format: `myjobs-bot/1.0 (+https://myjobs.fyi/bot; contact: bot@myjobs.fyi)`.
- **Robots.txt & Backoff:** Cache parsed `robots.txt` in Redis for 24 hours. Honor `Retry-After` headers and back off exponentially on HTTP 429.
- **SSRF Hardening:** `src/shared/ssrf.py` verifies resolved IP addresses across all redirect hops to prevent intranet scanning.

### 3.3 Stale-Job Expiry Policy
- **Soft Delist:** When an active posting is absent from its board for 3 consecutive checks (`missing_count >= 3`), mark `is_active = false`.
- **Hard Expiry:** A daily SQL routine retires postings untouched for >45 days:
  `UPDATE job_posting SET is_active = false, updated_at = now() WHERE is_active = true AND last_seen_at < now() - INTERVAL '45 days';`
- **Index Optimization:** Public feed indexes (`idx_jp_feed`, `idx_jp_location_ids`) filter on `WHERE is_active = true`, ensuring sub-10ms response times even as historical rows exceed millions.

### 3.4 Failure Alerting
- **Worker Heartbeat:** Worker sends a ping to **Healthchecks.io** (free tier: 20 checks) every 5 minutes. If no ping arrives for 15 minutes, an alert triggers to Telegram / Discord / Email.
- **Quarantine Alerts:** Boards with 5 consecutive errors (`consecutive_failures >= 5`) are set to `board_status = 'quarantined'`. A daily webhook reports newly quarantined boards for review.

### 3.5 "Last Updated" Indicator
Already provided in `/api/v1/stats` (`src/api/queries.py`) as `MAX(last_success_at) FROM job_board AS last_updated`.  
The Next.js frontend queries this endpoint (cached at edge for 30s) and renders a relative badge (e.g., *"Updated 4m ago"* with a pulsing green indicator).

---

## 4. Auth, Storage, Secrets, Backups & Observability

### 4.1 Authentication Options for Later
- **Auth.js (NextAuth v5) [Recommended]:** Runs inside Next.js, persists sessions directly to Postgres. **Cost: ₹0 forever.** Maximum independence, zero external vendor lock-in.
- **Supabase Auth:** Useful if hosted on Supabase; native JWT integration with Postgres RLS (`auth.uid()`). Free up to 50,000 MAU.
- **Clerk:** Polished UI components, free up to 10,000 MAU. Introduces proprietary lock-in and requires webhook sync to Postgres.

### 4.2 Resume Storage with Encryption at Rest
Resumes contain sensitive PII (contact info, employment history, compensation notes).
- **Storage Tier:** **Cloudflare R2** (S3-compatible, 10 GB free forever, **zero egress bandwidth fees**).
- **Envelope Encryption Workflow:**
  1. For each uploaded resume, generate a unique 256-bit Data Encryption Key (DEK).
  2. Encrypt document in memory with **AES-256-GCM** before uploading ciphertext to R2.
  3. Encrypt DEK using a Master Key stored in the server environment and save reference in `resume_file.enc_blob_key_ref`.
  4. Resumes decrypt only into ephemeral memory when compiling LaTeX templates or parsing profiles. Plaintext files never sit unencrypted at rest.

### 4.3 Secrets Management
- **Lean Setup:** Server environment file (`/etc/myjobs/.env` with `chmod 600`) loaded by systemd or Docker Compose.
- **Alternative:** **Infisical** or **Doppler** free tiers (up to 3 developers) for centralized secret rotation during deployments.

### 4.4 Automated Database Backups
- **Nightly Offsite Backup:** Run via cron on the VPS:
  `pg_dump -Fc crawler | age -r <key> | aws s3 cp - s3://myjobs-backups/pg-$(date +%F).dump.age --endpoint-url https://<id>.r2.cloudflarestorage.com`
- **Retention & Cost:** 7 daily and 4 weekly snapshots stored in Cloudflare R2 (~20–35 GB total ≈ ₹10–₹25/mo beyond the 10 GB free tier).
- **Verification:** Backup script pings Healthchecks.io upon successful completion.

### 4.5 Observability Stack (Free Tiers)
- **Uptime Monitoring:** **Better Stack (Better Uptime)** free tier (10 monitors, 3-minute checks, push/email alerts).
- **Error Tracking:** **Sentry** Developer Plan (free 5,000 errors/month) configured for FastAPI and Next.js.
- **Worker Metrics:** Local Prometheus endpoint (`src/metrics.py` on port 9091) or Healthchecks.io daemon status.

---

## 5. LLM Cost Model for Later

### 5.1 Access Strategy: BYOK vs. Server Key
To protect a solo developer from unpredictable API bills:
- **Server Key with Quotas:** New users receive 3 complimentary resume tailorings per month using cost-effective models.
- **Bring-Your-Own-Key (BYOK):** Power users provide their own OpenAI, Anthropic, or OpenRouter API key (stored encrypted at rest). All subsequent tailoring calls run against their key, eliminating platform liability.

### 5.2 Model Tiering (Bulk vs. Tailoring)

| Phase | Task | Model | Token Pricing | Est. Cost / Action |
|---|---|---|---|---|
| **Bulk Work** | Resume JSON extraction, taxonomy classification, skill matching. | **Gemini 1.5 Flash** or **DeepSeek-V3** | ~$0.075 / 1M in<br>~$0.30 / 1M out | **~₹0.05 – ₹0.15** per resume |
| **High-Precision Tailoring** | LaTeX bullet adaptation, ATS alignment, anti-fabrication verification (DECISIONS D10). | **Claude 3.5 Sonnet** | ~$3.00 / 1M in<br>~$15.00 / 1M out | **~₹0.80 – ₹1.50** per tailored draft |

### 5.3 Prompt Caching Optimization
Anthropic and OpenAI support prompt caching (up to 90% discount on cached input tokens).  
By caching the candidate's master profile, formatting instructions, and anti-fabrication validator rules, repeat tailoring runs drop to **~₹0.20 – ₹0.40** per run.

### 5.4 Fallback Circuit-Breaker Router
A Python wrapper handles all model invocations:
1. **Primary Route:** Direct request to Gemini 1.5 Flash (bulk) or Claude 3.5 Sonnet (tailoring).
2. **Circuit Breaker:** If 3 consecutive calls fail (HTTP 429, 502, or timeout), trip the circuit for 5 minutes.
3. **Fallback Route:** Automatically redirect traffic to **OpenRouter** (accessing DeepSeek or Llama 3 models), maintaining uninterrupted service during upstream outages.

---

## 6. Recommended Stack & Deployment Plan

### 6.1 The Concrete Recommended Stack

- **Compute & Persistence (Single VPS):** **Hetzner Cloud CPX21** (3 vCPU AMD, 4 GB RAM, 80 GB NVMe, €7.50/mo ~₹750/mo in Germany/Finland) or **Oracle Cloud Always Free Ampere A1 ARM** (4 OCPU, 24 GB RAM, ₹0/mo in Mumbai/Hyderabad).
  - **Docker Compose Services on VPS:**
    - Caddy web server (automatic HTTPS, Brotli, reverse proxy).
    - FastAPI feed API (`myjobs serve`, port 8080).
    - Python crawler daemon (`myjobs worker`, ~40 async workers).
    - Postgres 16 (local NVMe, `pg_trgm`, 2–5 GB active data).
    - Redis 7 (Alpine container, queues & token bucket rate limiting, <100 MB RAM).
- **Frontend:** **Cloudflare Pages** (Next.js in `web/`, ₹0/mo, unlimited bandwidth, edge caching across 20+ Indian PoPs).
- **Storage & Backups:** **Cloudflare R2** (encrypted resumes + encrypted DB dumps, 10 GB free tier: ₹0/mo).
- **Observability:** **Healthchecks.io** (worker heartbeat: ₹0/mo) + **Better Stack** (API uptime: ₹0/mo).
- **Auth (Phase 4):** **Auth.js (NextAuth v5)** with Postgres adapter (₹0/mo).

### 6.2 Monthly Cost Estimate (₹ / month)

*Note: All prices as of knowledge cutoff; verify before buying. Includes currency conversion ($1 ≈ ₹85, €1 ≈ ₹92) and 18% GST.*

| Component | Low-End (Free Tiers Maximized) | Expected / Practical Baseline | High-End (Buffer / Growth) |
|---|---|---|---|
| **Compute / VPS** | **₹0** (Oracle Cloud Always Free ARM) | **₹750** (Hetzner CPX21: 3 vCPU / 4 GB) | **₹1,150** (Hetzner CX32: 4 vCPU / 8 GB) |
| **Postgres 16** | **₹0** (Self-hosted on VPS) | **₹0** (Self-hosted on VPS) | **₹0** (Self-hosted on VPS) |
| **Redis 7** | **₹0** (Self-hosted on VPS) | **₹0** (Self-hosted on VPS) | **₹0** (Self-hosted on VPS) |
| **Frontend** | **₹0** (Cloudflare Pages) | **₹0** (Cloudflare Pages) | **₹0** (Cloudflare Pages) |
| **Object Storage (R2)** | **₹0** (<10 GB free tier) | **₹0** (<10 GB free tier) | **₹50** (Minor overage ~15 GB) |
| **Observability & Alerts** | **₹0** (Healthchecks.io + Better Stack) | **₹0** (Free tiers) | **₹0** (Free tiers) |
| **Domain Name** | **₹80** (~₹950/year prorated) | **₹80** (~₹950/year prorated) | **₹120** (.com / .fyi premium) |
| **Total Monthly Cost** | **~₹80 / month** | **~₹830 / month** | **~₹1,320 / month** |

---

### 6.3 First 5 Steps to Deploy

1. **Provision VPS & Harden Security:**
   - Deploy a Hetzner Cloud CPX21 instance (Ubuntu 24.04 LTS) or an Oracle Cloud Always Free Ampere A1 VM (Mumbai/Hyderabad).
   - Configure SSH key authentication, disable root password login, and enable UFW allowing only ports `22` (SSH), `80` (HTTP), and `443` (HTTPS).
2. **Install Docker Engine & Configure Environment:**
   - Install Docker Engine and the Docker Compose plugin.
   - Clone the repository to `/opt/myjobs`.
   - Copy `.env.example` to `/opt/myjobs/.env` (`chmod 600`), configuring production database credentials, secret keys, and Redis settings.
3. **Initialize Database & Seed Reference Data:**
   - Launch persistence containers: `docker compose up -d postgres redis`.
   - Apply schema migrations: `docker compose run --rm crawler alembic upgrade head`.
   - Seed GeoNames and taxonomy reference tables:
     ```bash
     docker compose run --rm crawler python scripts/load_geonames.py
     docker compose run --rm crawler python scripts/populate_taxonomy.py
     ```
4. **Deploy Caddy & Start Backend Daemons:**
   - Create `/etc/caddy/Caddyfile` mapping `api.myjobs.fyi` to reverse-proxy `127.0.0.1:8080` with automatic Let's Encrypt certificates.
   - Start FastAPI (`myjobs serve`) and the crawler worker (`myjobs worker`) using Docker Compose with `restart: unless-stopped`.
5. **Deploy Frontend & Verify Freshness:**
   - Connect the repository's `web/` directory to Cloudflare Pages.
   - Set environment variable `NEXT_PUBLIC_API_URL=https://api.myjobs.fyi`.
   - Point DNS to Cloudflare, open the site, and verify that `/api/v1/stats` returns HTTP 200 with a working last-updated timestamp.

## Reviewer notes (orchestrator)
- **RAM:** 4 GB (CPX21) is tight once Playwright boards run alongside Postgres and 40 workers. Either run the browser
  worker on a schedule (e.g. every 6 h) instead of continuously, or start on the 8 GB tier or the Oracle free ARM box
  (24 GB, ARM; Playwright Chromium does support linux-arm64).
- **Next.js on Cloudflare Pages:** this needs the OpenNext Cloudflare adapter for server rendering. If that adds friction,
  Vercel's hobby tier is the zero-config fallback for a non-commercial demo.
- The prices are the drafter's estimates as of its cutoff. Verify them before buying.
