"""Stand-in for jobseek's optional Go runtime (``src.runtime.*_go``).

Vendored jobseek code calls ``<module>.enabled()``/``eligible()`` and falls back to Python when
they return False. We don't ship the Go binaries, so every fast path reports disabled.
"""

from __future__ import annotations


class _Disabled:
    @staticmethod
    def enabled(*_args, **_kwargs) -> bool:
        return False

    @staticmethod
    def eligible(*_args, **_kwargs) -> bool:
        return False


dom_go_http = dom_go_parse = job_enrichment_go = jsonld_go_detail = _Disabled()
