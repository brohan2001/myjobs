# Deployment plan (₹0, D24)

One Oracle Cloud Always Free VM runs everything. Free-tier limits change; check them when signing up.

## Why one free VM
Measured on 2026-10-12: Postgres is **2.8 GB** (~400k active postings) and Redis about 90 MB. Free managed Postgres tiers
(Neon 0.5 GB, Supabase 500 MB) are too small, and Upstash's free command quota is too low for the worker. The only free option
that fits everything is a free VM.

## The stack
- **One Oracle Cloud Always Free Ampere A1 VM** (ARM, up to 4 OCPU / 24 GB RAM, up to 200 GB block storage), in the Mumbai or
  Hyderabad region. Docker Compose runs:
  - Postgres 16 and Redis 7, as in `docker-compose.yml` today.
  - `myjobs worker` (with the browser; Playwright Chromium has linux-arm64 builds).
  - `myjobs serve` (API).
  - `web/` with `next start` (Node), so no Cloudflare or Vercel adapter is needed.
  - Caddy in front, with automatic HTTPS: `/` goes to Next.js and `/api` to FastAPI.
- **Hostname:** a free DuckDNS subdomain (e.g. `myjobs.duckdns.org`) pointed at the VM's public IP. Caddy gets the Let's Encrypt
  certificate. A paid domain can come later without any other change.
- **Backups:** a nightly `pg_dump | gzip` to Oracle Object Storage (Always Free includes 20 GB), keeping the last 7.
- **Monitoring:** Healthchecks.io free tier, pinged by a cron job that runs `myjobs health`. It alerts by email when the ping
  stops or the health check fails.

| Component | Where | Cost |
|---|---|---|
| Postgres, Redis, worker, API, web, Caddy | Oracle A1 VM | ₹0 |
| Hostname and TLS | DuckDNS + Let's Encrypt | ₹0 |
| Backups | Oracle Object Storage | ₹0 |
| Monitoring | Healthchecks.io free | ₹0 |
| **Total** | | **₹0 / month** |

## Caveats
- **Sign-up needs a card** to verify identity. Always Free resources are not charged. Do **not** upgrade to Pay-As-You-Go:
  that's where charges can start.
- **"Out of capacity"** for A1 in Indian regions is common. Retry at a different time, or try the other Indian region.
- **Idle reclamation:** Oracle may reclaim Always Free VMs that look idle for a week. A continuous crawler is not idle, but keep
  the off-VM backups anyway.
- **Single box:** if the VM dies, restore it from the latest dump (about 30 min of work). That's acceptable for a free public feed.

## Fallbacks (still ₹0)
1. **Run it on your own machine** and expose it with a free Cloudflare Tunnel. A stable hostname needs a domain on Cloudflare;
   without one, a Quick Tunnel's `trycloudflare.com` URL changes on every restart. Good for showing people, not for uptime.
2. **Google Cloud e2-micro (always free, US regions only):** 1 GB RAM is too small for Postgres plus the browser worker. Only
   viable with `--no-browser` and a trimmed dataset.

## First steps to deploy
1. Create the Oracle account; launch an A1 VM (Ubuntu 24.04 arm64) with a 100 GB boot volume. Open ports 80 and 443 in the
   security list **and** in the VM's iptables (Oracle images block them by default). SSH key login only.
2. Install Docker; clone the repo to `/opt/myjobs`; create `.env` (`chmod 600`) with production passwords.
3. Run `docker compose up -d`, `alembic upgrade head`, `scripts/load_geonames.py` and `scripts/populate_taxonomy.py`, then
   `myjobs sync`.
4. Add the worker, API, web and Caddy services, all with `restart: unless-stopped`; point DuckDNS at the VM.
5. Set up the backup and Healthchecks cron jobs; open the site and check that `/api/v1/stats` shows a recent "last updated".

Before step 1, the repo needs production compose services for the worker, API, web and Caddy, plus a Caddyfile and a backup
script. Not written yet: Phase 4 stays proposal-only until the user approves this section.

