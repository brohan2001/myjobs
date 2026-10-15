"""Stable content hash for change detection, stored as a Postgres bigint."""

from __future__ import annotations

import hashlib
import struct


def content_hash(data: str) -> int:
    """Return a signed int64 hash of ``data``."""
    digest = hashlib.sha256(data.encode("utf-8")).digest()
    return struct.unpack(">q", digest[:8])[0]
