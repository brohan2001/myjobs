"""Extractor for notice period requirements in Indian job postings.

Exposes extract_notice_period(text: str | None) -> int | None returning the
longest notice period an Indian job posting accepts, in days.
0 = immediate joiners only; None = not stated.
"""

from __future__ import annotations

import html
import re

# HTML tag stripping and whitespace normalization
_TAG_RE = re.compile(r"<!--.*?-->|<[a-zA-Z/!][^>]*>", re.DOTALL)
_WS_RE = re.compile(r"\s+")

# Connector words and punctuation between notice-period keywords and the duration/range
_CONNECTOR = (
    r"(?:"
    r"[\s:\-–—=/()<>=,]|"
    r"\b(?:"
    r"of|"
    r"is|"
    r"are|"
    r"should\s+be|"
    r"must\s+be|"
    r"can\s+be|"
    r"to\s+be|"
    r"within|"
    r"up\s+to|"
    r"in|"
    r"max(?:\.|imum)?|"
    r"min(?:\.|imum)?|"
    r"less\s+than|"
    r"more\s+than|"
    r"under|"
    r"below|"
    r"at\s+most|"
    r"not\s+more\s+than|"
    r"not\s+exceeding|"
    r"preferably|"
    r"around|"
    r"approx(?:\.|imately)?|"
    r"strictly|"
    r"between"
    r")\b"
    r")*"
)

# Matches single duration or range (e.g. "0-30 days", "immediate to 15 days", "1 to 2 months", "30 days").
# Group 1 captures the upper bound number, Group 2 captures the unit.
_DURATION_OR_RANGE = (
    r"(?:"
    r"(?:immediate(?:ly)?|\d+)"
    r"\s*(?:days?|weeks?|months?)?"
    r"\s*(?:to|-|–|—|/)\s*"
    r")?"
    r"(\d+)"
    r"\s*(days?|weeks?|months?)"
    r"\b"
)

# Context 1: Prefix "notice period" or "NP:"
_PREFIX_NP_RE = re.compile(
    r"\b(?:notice[\s\-]+period|np\s*[:\-–—])"
    + _CONNECTOR
    + _DURATION_OR_RANGE,
    re.IGNORECASE,
)

# Context 2: Suffix "notice period"
_SUFFIX_NP_RE = re.compile(
    r"(?:\b(?:max(?:\.|imum)?|up\s+to|within|min(?:\.|imum)?)\s+)?"
    + _DURATION_OR_RANGE
    + r"\s+(?:of\s+)?notice[\s\-]+period\b",
    re.IGNORECASE,
)

# Context 3: "join within" or "can join"
_JOIN_WITHIN_RE = re.compile(
    r"\b(?:can\s+join|(?:(?:able\s+to|should\s+be\s+able\s+to)\s+)?join\s+(?:within|in))\s+"
    + r"(?:\b(?:max(?:\.|imum)?|up\s+to)\s+)?"
    + _DURATION_OR_RANGE,
    re.IGNORECASE,
)

# Context 4: Suffix "joiners" / "joiner"
_SUFFIX_JOINER_RE = re.compile(
    _DURATION_OR_RANGE
    + r"\s+joiners?\b",
    re.IGNORECASE,
)

# Context 5: Immediate range with "notice" (e.g. "Immediate - 30 days notice")
_IMMEDIATE_NOTICE_RE = re.compile(
    r"\bimmediate\s*(?:to|-|–|—|/)\s*(\d+)\s*(days?|weeks?|months?)\s+notice\b",
    re.IGNORECASE,
)

# Immediate joiners (0 days)
_IMMEDIATE_JOINER_RE = re.compile(r"\bimmediate\s+joiners?\b", re.IGNORECASE)

_JOIN_IMMEDIATELY_RE = re.compile(
    r"\b(?:(?:can\s+|able\s+to\s+|should\s+be\s+able\s+to\s+)?join\s+immediately|immediate\s+joining)\b",
    re.IGNORECASE,
)

_NOTICE_PERIOD_IMMEDIATE_RE = re.compile(
    r"\b(?:notice[\s\-]+period|np\s*[:\-–—])" + _CONNECTOR + r"immediate(?:ly)?\b",
    re.IGNORECASE,
)

# Max allowed days to ignore absurd values (values > 180 days are ignored)
_MAX_NOTICE_DAYS = 180


def _to_days(num_str: str, unit_str: str) -> int:
    num = int(num_str)
    unit = unit_str.lower()
    if unit.startswith("day"):
        return num
    elif unit.startswith("week"):
        return num * 7
    elif unit.startswith("month"):
        return num * 30
    return num


def _strip_html(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def extract_notice_period(text: str | None) -> int | None:
    """Extract the longest accepted notice period in days from text or HTML.

    Returns:
        0 for immediate joiners only.
        The longest accepted notice period in days (<= 180).
        None if not stated or if values exceed 180 days.
    """
    if text is None:
        return None

    cleaned = _strip_html(text)
    if not cleaned:
        return None

    candidates: list[int] = []

    # Check for immediate joiner indications (0 days)
    if (
        _IMMEDIATE_JOINER_RE.search(cleaned)
        or _JOIN_IMMEDIATELY_RE.search(cleaned)
        or _NOTICE_PERIOD_IMMEDIATE_RE.search(cleaned)
    ):
        candidates.append(0)

    # Check all notice-period duration patterns
    for pattern in (
        _PREFIX_NP_RE,
        _SUFFIX_NP_RE,
        _JOIN_WITHIN_RE,
        _SUFFIX_JOINER_RE,
        _IMMEDIATE_NOTICE_RE,
    ):
        for m in pattern.finditer(cleaned):
            days = _to_days(m.group(1), m.group(2))
            if 0 <= days <= _MAX_NOTICE_DAYS:
                candidates.append(days)

    return max(candidates, default=None)
