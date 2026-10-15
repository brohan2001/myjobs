"""No-op stand-in for jobseek's Prometheus metrics (D26).

Vendored jobseek code imports counters, gauges and histograms by name and calls ``labels()``,
``inc()``, ``observe()`` and friends. Nothing scrapes them here, so every name resolves to
one object that accepts any call (helpers like ``http_retry_host`` included). ``myjobs health`` is the operator signal instead.
"""

from __future__ import annotations

from contextlib import nullcontext


class _NoOpMetric:
    def labels(self, *_args, **_kwargs) -> _NoOpMetric:
        return self

    def __call__(self, *_args, **_kwargs) -> _NoOpMetric:
        # Also stands in for label helpers such as ``http_retry_host(url)``.
        return self

    def __getattr__(self, _name):
        return _noop

    def time(self):
        return nullcontext()


def _noop(*_args, **_kwargs) -> None:
    return None


_METRIC = _NoOpMetric()


def __getattr__(name: str) -> _NoOpMetric:
    return _METRIC
