"""Crawler settings — pydantic-settings based configuration.

All settings are read from environment variables (and .env / .env.local files).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    local_database_url: str = "postgresql://crawler:crawler@localhost:5432/crawler"

    # Proxy provider — applies to hosts with ``"proxy": true`` in
    # ``monitor_config`` / ``scraper_config`` (``data/boards.csv``).
    proxy_provider: str = "none"  # none | webshare | decodo
    webshare_proxy_url: str = ""
    webshare_proxy_urls: list[str] = []
    webshare_proxy_canary_slot: int | None = None
    decodo_proxy_url: str = ""

    # SSRF guard
    internal_hosts_allow: str = ""

    # Redis (local instance)
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 60
    throttle_delay_default: float = 2.0
    throttle_delay_ats: float = 0.5

    # Inflight lease + reaper
    inflight_lease_ttl_seconds: int = 600
    inflight_heartbeat_interval_seconds: int = 120
    reaper_interval_seconds: int = 30
    reaper_batch_size: int = 200
    reaper_max_strikes: int = 5

    # Graceful drain on SIGTERM/SIGINT
    shutdown_grace_seconds: int = 30

    # Public API
    api_rate_limit_per_minute: int = 120
    api_cors_origins: str = ""  # comma-separated; empty = same-origin only
    admin_token: str = ""  # bearer token for /api/admin/*; empty disables the admin routes (D31)

    log_level: str = "INFO"
    worker_id_prefix: str = ""
    crawler_db_pool_max: int = 20

    # Pipeline concurrency (per-instance)
    discovery_concurrency: int = 40
    monitor_concurrency: int = 30  # per process; the other 10 coroutines keep page scrapes moving
    browser_monitor_concurrency: int = 6  # one Chromium each: ~20 crashed launches and blew the memory budget (D30)
    raw_buffer_size: int = 10
    done_buffer_size: int = 10
    writeback_concurrency: int = 5
    # Share of claims that try page scrapes before board checks, so a check backlog can't starve them
    scrape_claim_share: float = 0.3
    cpu_threads: int = 1

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")


settings = Settings()
