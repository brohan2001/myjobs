"""Indian salary formats (INR/LPA) extraction.

Parses Indian salary formats: LPA, lakh/lakhs/L, Cr/crore, ₹/Rs/INR prefixes,
Indian digit grouping (8,00,000), and monthly figures into SalaryRange instances.
"""
from __future__ import annotations

import re

from src.core.salary_extract import SalaryRange

_INR_CONTEXT_RE = re.compile(
    r"₹|\b(?:Rs\.?|INR|LPA|lakhs?|lacs?|crores?|cr)\b",
    re.IGNORECASE,
)

_CURRENCY_RE = r"(?:₹|Rs\.?|INR)"
_UNIT_RE = r"(?:LPA|L\.P\.A\.|lakhs?|lacs?|cr(?:ores?)?\.?|L)"
_SEP_RE = r"(?:[-–—]|\bto\b|\btill\b|\buntil\b)"
_FULL_NUM_STR = r"(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+|\d{3,})(?:\.\d{1,2})?"

_MONTHLY_RE = re.compile(
    r"\b(?:per\s+month|monthly|pm|p\.m\.)\b|/month|/mo\b",
    re.IGNORECASE,
)
_YEARLY_RE = re.compile(
    r"\b(?:lpa|l\.p\.a\.|per\s+annum|annually|annual|per\s+year|yearly|p\.a\.|pa)\b|/year|/yr\b|/annum",
    re.IGNORECASE,
)

_UNIT_RANGE_RE = re.compile(
    rf"(?:(?P<cur1>{_CURRENCY_RE})?\s*(?P<num1>\d+(?:\.\d+)?)\s*(?P<unit1>{_UNIT_RE})\s*(?P<sep>{_SEP_RE})\s*(?P<cur2>{_CURRENCY_RE})?\s*(?P<num2>\d+(?:\.\d+)?)(?:\s*(?P<unit2>{_UNIT_RE}))?\b"
    rf"|(?P<cur1_alt>{_CURRENCY_RE})?\s*(?P<num1_alt>\d+(?:\.\d+)?)\s*(?P<sep_alt>{_SEP_RE})\s*(?P<cur2_alt>{_CURRENCY_RE})?\s*(?P<num2_alt>\d+(?:\.\d+)?)\s*(?P<unit2_alt>{_UNIT_RE})\b)",
    re.IGNORECASE,
)

_FULL_RANGE_RE = re.compile(
    rf"(?P<cur1>{_CURRENCY_RE})?\s*"
    rf"(?P<num1>{_FULL_NUM_STR})\s*"
    rf"(?P<sep>{_SEP_RE})\s*"
    rf"(?P<cur2>{_CURRENCY_RE})?\s*"
    rf"(?P<num2>{_FULL_NUM_STR})\b"
    rf"(?:\s*(?P<cur_suff>{_CURRENCY_RE}))?",
    re.IGNORECASE,
)

_UNIT_SINGLE_RE = re.compile(
    rf"(?:(?P<cur>{_CURRENCY_RE})\s*)?"
    rf"(?P<num>\d+(?:\.\d+)?)\s*"
    rf"(?P<unit>{_UNIT_RE})\b",
    re.IGNORECASE,
)

_FULL_SINGLE_RE = re.compile(
    rf"(?:(?P<cur_pre>{_CURRENCY_RE})\s*(?P<num>{_FULL_NUM_STR})\b"
    rf"|(?P<num_alt>{_FULL_NUM_STR})\s*(?P<cur_post>{_CURRENCY_RE})\b)",
    re.IGNORECASE,
)


def _clean_number(s: str) -> float:
    return float(s.replace(",", "").replace(" ", "").strip())


def _parse_unit(unit_str: str | None) -> tuple[int, str | None]:
    if not unit_str:
        return 1, None
    u = unit_str.lower().replace(".", "").strip()
    if u == "lpa":
        return 100_000, "yearly"
    elif u in ("cr", "crore", "crores"):
        return 10_000_000, "yearly"
    elif u in ("l", "lakh", "lakhs", "lac", "lacs"):
        return 100_000, None
    return 1, None


def _detect_period(surrounding_text: str, default_period: str | None = None) -> str:
    if _MONTHLY_RE.search(surrounding_text):
        return "monthly"
    if _YEARLY_RE.search(surrounding_text):
        return "yearly"
    if default_period:
        return default_period
    return "yearly"


def _is_valid_range(lo: int, hi: int | None, period: str) -> bool:
    if period == "monthly":
        if lo < 5_000:
            return False
        if hi is not None and hi < 5_000:
            return False
    elif period == "yearly":
        if lo < 100_000:
            return False
        if hi is not None and hi < 100_000:
            return False
    return True


def extract_inr(text: str) -> list[SalaryRange]:
    """Extract INR salary figures from text.

    Returns a list of SalaryRange instances. If no INR context is present,
    or figures fall below threshold (₹5,000/mo, ₹1,00,000/yr), returns [].
    """
    if not text:
        return []

    if not _INR_CONTEXT_RE.search(text):
        return []

    occupied_spans: list[tuple[int, int]] = []
    results: list[tuple[int, SalaryRange]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(max(s, start) < min(e, end) for s, e in occupied_spans)

    # 1. Unit ranges (e.g. 10-15 LPA, ₹12L - ₹18L per annum)
    for m in _UNIT_RANGE_RE.finditer(text):
        if m.group("num1") is not None:
            cur1 = m.group("cur1")
            num1 = m.group("num1")
            unit1 = m.group("unit1")
            cur2 = m.group("cur2")
            num2 = m.group("num2")
            unit2 = m.group("unit2")
        else:
            cur1 = m.group("cur1_alt")
            num1 = m.group("num1_alt")
            unit1 = None
            cur2 = m.group("cur2_alt")
            num2 = m.group("num2_alt")
            unit2 = m.group("unit2_alt")

        u1 = unit1 or unit2
        u2 = unit2 or unit1

        # If unit is 'L' (and not LPA/Lakh/Cr), require currency symbol
        is_l = (u1 and u1.lower() == "l") or (u2 and u2.lower() == "l")
        if is_l and not (cur1 or cur2):
            continue

        mult1, def_p1 = _parse_unit(u1)
        mult2, def_p2 = _parse_unit(u2)

        try:
            val1 = int(round(_clean_number(num1) * mult1))
            val2 = int(round(_clean_number(num2) * mult2))
        except ValueError:
            continue

        lo = min(val1, val2)
        hi = max(val1, val2)

        start = m.start()
        end = m.end()

        if _overlaps(start, end):
            continue

        surrounding = text[max(0, start - 40) : min(len(text), end + 40)]
        period = _detect_period(surrounding, def_p2 or def_p1)

        if not _is_valid_range(lo, hi, period):
            continue

        occupied_spans.append((start, end))
        results.append((start, SalaryRange(min=lo, max=hi, currency="INR", period=period)))

    # 2. Full number ranges (e.g. INR 8,00,000 - 12,00,000 per annum, ₹50,000 - ₹70,000/month)
    for m in _FULL_RANGE_RE.finditer(text):
        start = m.start()
        end = m.end()

        if _overlaps(start, end):
            continue

        cur1 = m.group("cur1")
        cur2 = m.group("cur2")
        cur_suff = m.group("cur_suff")

        leading_window = text[max(0, start - 30) : start]
        has_currency = bool(cur1 or cur2 or cur_suff or re.search(_CURRENCY_RE, leading_window, re.IGNORECASE))
        if not has_currency:
            continue

        try:
            val1 = int(round(_clean_number(m.group("num1"))))
            val2 = int(round(_clean_number(m.group("num2"))))
        except ValueError:
            continue

        lo = min(val1, val2)
        hi = max(val1, val2)

        surrounding = text[max(0, start - 40) : min(len(text), end + 40)]
        period = _detect_period(surrounding, "yearly")

        if not _is_valid_range(lo, hi, period):
            continue

        occupied_spans.append((start, end))
        results.append((start, SalaryRange(min=lo, max=hi, currency="INR", period=period)))

    # 3. Unit singles (e.g. up to 25 LPA, CTC 1.2 Cr, 18 lakh per annum)
    for m in _UNIT_SINGLE_RE.finditer(text):
        start = m.start()
        end = m.end()

        if _overlaps(start, end):
            continue

        unit = m.group("unit")
        cur = m.group("cur")

        if unit.lower() == "l" and not cur:
            continue

        mult, def_period = _parse_unit(unit)
        try:
            val = int(round(_clean_number(m.group("num")) * mult))
        except ValueError:
            continue

        surrounding = text[max(0, start - 40) : min(len(text), end + 40)]
        period = _detect_period(surrounding, def_period)

        if not _is_valid_range(val, None, period):
            continue

        occupied_spans.append((start, end))
        results.append((start, SalaryRange(min=val, max=None, currency="INR", period=period)))

    # 4. Full number singles (e.g. Stipend: ₹40,000 per month, INR 2400000 annually)
    for m in _FULL_SINGLE_RE.finditer(text):
        start = m.start()
        end = m.end()

        if _overlaps(start, end):
            continue

        num_str = m.group("num") or m.group("num_alt")
        try:
            val = int(round(_clean_number(num_str)))
        except ValueError:
            continue

        surrounding = text[max(0, start - 40) : min(len(text), end + 40)]
        period = _detect_period(surrounding, "yearly")

        if not _is_valid_range(val, None, period):
            continue

        occupied_spans.append((start, end))
        results.append((start, SalaryRange(min=val, max=None, currency="INR", period=period)))

    results.sort(key=lambda item: item[0])
    return [r for _, r in results]
