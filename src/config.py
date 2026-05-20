"""Crawler settings — pydantic-settings based configuration.

All settings are read from environment variables (and .env / .env.local files).
Scoring/keyword constants live in src/scoring_config.py so they don't conflict
with this Settings class.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    local_database_url: str = "postgresql://crawler:crawler@localhost:5432/crawler"

    # Proxy provider — applies to hosts with ``"proxy": true`` in
    # ``monitor_config`` / ``scraper_config`` (``data/boards.csv``).
    proxy_provider: str = "none"  # none | webshare | decodo
    webshare_proxy_url: str = ""
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

    log_level: str = "INFO"
    worker_id_prefix: str = ""
    crawler_db_pool_max: int = 10
    metrics_port: int = 9091

    # Pipeline concurrency (per-instance)
    discovery_concurrency: int = 20
    monitor_concurrency: int = 5
    raw_buffer_size: int = 10
    done_buffer_size: int = 10
    writeback_concurrency: int = 5
    cpu_threads: int = 1

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")


settings = Settings()
