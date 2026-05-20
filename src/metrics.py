"""No-op metrics stubs for jobseek vendored code.

The vendored src/core/ and src/shared/ monitors import Prometheus counters from
this module.  We don't run prometheus_client, so we stub everything out.
"""
from __future__ import annotations

from urllib.parse import urlparse


class _NoopCounter:
    def labels(self, **_kwargs: object) -> "_NoopCounter":
        return self

    def inc(self, amount: float = 1) -> None:
        pass


def http_retry_host(url: str) -> str:
    """Extract hostname from *url* — used as a Prometheus label."""
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


http_retry_attempts_total = _NoopCounter()
http_retry_empty_200_total = _NoopCounter()
http_retry_transient_403_total = _NoopCounter()
api_sniffer_fallback_failed_total = _NoopCounter()
browser_navigate_fallback_total = _NoopCounter()
browser_content_retry_total = _NoopCounter()
browser_headless_coerced_total = _NoopCounter()


def __getattr__(name: str) -> _NoopCounter:
    """Return a no-op counter for any unknown metric (forward-compat with new monitors)."""
    return _NoopCounter()
