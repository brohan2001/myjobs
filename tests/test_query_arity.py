"""Guards against column/placeholder drift in the rich-posting write path."""
from __future__ import annotations

import re

from src.queries import monitor as q


def _insert_columns(sql: str) -> list[str]:
    cols = sql.split("INSERT INTO job_posting", 1)[1].split("VALUES", 1)[0]
    return [c.strip() for c in cols.strip().strip("()").split(",") if c.strip()]


def _insert_values(sql: str) -> list[str]:
    vals = sql.split("VALUES", 1)[1].split("ON CONFLICT", 1)[0]
    return [v.strip() for v in vals.strip().strip("()").split(",") if v.strip()]


def test_insert_rich_job_columns_match_values():
    for sql in (q._INSERT_RICH_JOB, q._INSERT_RICH_JOB_ENRICH):
        assert len(_insert_columns(sql)) == len(_insert_values(sql))


def test_insert_rich_job_placeholders_are_contiguous():
    for sql in (q._INSERT_RICH_JOB, q._INSERT_RICH_JOB_ENRICH):
        nums = sorted(int(n) for n in re.findall(r"\$(\d+)", sql))
        assert nums == list(range(1, len(nums) + 1))


def test_rich_updates_temp_table_covers_update_columns():
    body = q._CREATE_RICH_UPDATES_TEMP.split("(", 1)[1].rsplit(")", 1)[0]
    names = {part.strip().split()[0] for part in body.split(",") if part.strip()}
    used = set(re.findall(r"u\.(\w+)", q._BATCH_UPDATE_RICH_CONTENT))
    assert used <= names
