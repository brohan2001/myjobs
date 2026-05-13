from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_CONFIGURED: set[str] = set()

_RESERVED_LOG_KEYS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key not in _RESERVED_LOG_KEYS:
                out[key] = val
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"myjobs.{name}")
    if name not in _CONFIGURED:
        logger.setLevel(_LOG_LEVEL)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
        _CONFIGURED.add(name)
    return logger


# ── Structured event helpers ──────────────────────────────────────────────────

def log_scrape_start(logger: logging.Logger, company: str, ats_type: str) -> None:
    logger.info("scrape_start", extra={"company": company, "ats_type": ats_type})


def log_scrape_complete(
    logger: logging.Logger, company: str, ats_type: str, scraped: int, new: int
) -> None:
    logger.info(
        "scrape_complete",
        extra={"company": company, "ats_type": ats_type, "scraped": scraped, "new": new},
    )


def log_scrape_failure(
    logger: logging.Logger, company: str, ats_type: str, error: str
) -> None:
    logger.error(
        "scrape_failure",
        extra={"company": company, "ats_type": ats_type, "error": error},
    )


def log_empty_response(
    logger: logging.Logger, company: str, ats_type: str, url: str
) -> None:
    logger.warning(
        "empty_response",
        extra={"company": company, "ats_type": ats_type, "url": url},
    )


def log_rate_limited(
    logger: logging.Logger, company: str, ats_type: str, retry_after: float
) -> None:
    logger.warning(
        "rate_limited",
        extra={"company": company, "ats_type": ats_type, "retry_after_s": retry_after},
    )


def log_schema_drift(
    logger: logging.Logger,
    company: str,
    ats_type: str,
    unexpected_keys: list[str],
    missing_keys: list[str],
) -> None:
    logger.warning(
        "schema_drift",
        extra={
            "company": company,
            "ats_type": ats_type,
            "unexpected_keys": unexpected_keys,
            "missing_keys": missing_keys,
        },
    )
