"""Heuristic extraction of years-of-experience requirements from job HTML.

Design goal: **zero false positives**.  We only return experience data when
the text unambiguously states a number of years in the context of a
professional requirement.

Returns the minimum years required.  When multiple requirements appear
(e.g. "5+ years of software development" and "3+ years of design"), we
return the *maximum* across all stated minimums — this represents the
most senior requirement the candidate must meet.
"""

from __future__ import annotations

import re
from html import unescape
from dataclasses import dataclass

# ── Result type ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ExperienceRequirement:
    min_years: int
    max_years: int | None  # None when "5+ years" (open-ended)


# ── HTML → plain text ────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(html: str) -> str:
    text = unescape(_TAG_RE.sub(" ", html))
    return _WS_RE.sub(" ", text).strip()


# ── Main pattern ─────────────────────────────────────────────────────
#
# Matches:
#   "5+ years of experience"
#   "3-5 years of software development experience"
#   "5 years of experience"
#   "1+ years' experience"
#   "10+ years of relevant experience"
#   "7+ years of engineering experience"
#
# The pattern requires an experience-confirming suffix to avoid matching
# things like "15 years, Amazon has been..."

# Pattern A: "N+ years of ... experience" (English and multilingual)
_EXPERIENCE_RE = re.compile(
    r"(?:at\s+least\s+|minimum\s+|mindestens\s+|au\s+moins\s+|minimo\s+)?"
    r"(?<![\d.\-–—])(?<!to )(\d{1,2})(?:\.\d)?"  # min years (7.5 reads as 7), not the end of a range ("8-10+ years")
    r"\s*"
    r"(?:"
    r"\s*[+＋]"  # "5+", "5 +"
    r"|\s*(?:[-–—]|to)\s*(\d{1,2})(?:\.\d)?\s*[+＋]?"  # "3-5", "3 to 5", "7-10+", "5-6 +" → captures max
    r")?"
    r"\s*-?\s*"  # "6-year experience"
    r"(?:years?|yrs?|Jahre?|ans?|anni?|años?|jaar|år)"  # multilingual "year(s)"
    r"(?:\(s\))?"  # "year(s)"
    r"['’s]*"  # "years'" or "years's"
    r"\s+"
    r"("  # capture experience context
    r"(?:of\s+|d['’]\s*|di\s+|de\s+|an\s+|van\s+)?"
    r"(?:relevant\s+|professional\s+|hands[- ]on\s+|direct\s+|equivalent\s+|"
    r"progressive\s+|practical\s+|demonstrated?\s+|proven\s+|"
    r"non-internship\s+|full[- ]time\s+|industry\s+|related\s+|"
    r"minimum\s+|total\s+|combined\s+|solid\s+|"
    r"[\w]+\s+){0,3}"  # up to 3 qualifying adjectives / domain words
    r"(?:"
    # Must end with one of these experience-confirming words
    r"experience|expereince|experiance"
    r"|Erfahrung"
    r"|expérience"
    r"|esperienza"
    r"|experiencia"
    r"|ervaring"  # Dutch
    r"|erfarenhet"  # Swedish
    r"|erfaring"  # Danish/Norwegian
    r"|management"
    r"|(?:software |product |project |program )?(?:development|engineering)"
    r"|leadership"
    r"|consulting"
    r"|work(?:ing)?\s+(?:experience|in)"
    r"|Berufserfahrung"  # German compound
    r")"
    # "8+ years as a software engineer", "5+ years in test automation"
    r"|(?:in|as|on|within)\s+(?:an?\s+|the\s+)?[A-Za-z]"
    r")",
    re.IGNORECASE,
)

# Pattern B: Reversed word order (German/French/Italian)
#   "Erfahrung von mindestens 5 Jahren"
#   "expérience de 3 ans minimum"
#   "esperienza di almeno 5 anni"
_EXPERIENCE_REVERSED_RE = re.compile(
    r"(?:Erfahrung|Berufserfahrung|expérience|esperienza|experiencia|ervaring)"
    r"\s+(?:von\s+)?(?:mindestens\s+|d['’]\s*(?:au\s+moins\s+)?|"
    r"di\s+(?:almeno\s+)?|de\s+(?:al\s+menos\s+)?|van\s+(?:minimaal\s+)?)?"
    r"(\d{1,2})"  # min years
    r"\s*(?:[+＋]|\s*[-–—]\s*(\d{1,2}))?"  # optional + or range
    r"\s*(?:Jahren?|ans?|anni?|años?|jaar|år)",
    re.IGNORECASE,
)

# Pattern C: "experience" then the years, with or without a colon, common on Indian boards
#   "Experience: 3-5 Years", "Total Experience: 6-9 Years", "Years of Exp: 10 to 15 years", "Experience: >10 YEARS",
#   "Experience Required: 4+ yrs", "Experience 10-20 years", "Exp- 6+ years", "Experience (7+ years)",
#   "Experience between 4-7yrs", "Experience: Typically 4–8 years", "relevant experience of 2 - 5 years"
_EXPERIENCE_LABEL_RE = re.compile(
    r"\b(?:experience|expereince|experiance|exp)\.?(?:\s+(?:required|range|level))?"
    r"\s*[-:：–(]?\s*"
    r"(?:(?:of|for|from|between|typically|minimum|min\.?|at\s+least|over|around|approx\.?)\s+|>\s*)*"
    r"(\d{1,2})(?:\.\d)?"
    r"\s*(?:[+＋]|\s*(?:[-–—]|to)\s*(\d{1,2})(?:\.\d)?\s*[+＋]?)?"
    r"\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)

# Pattern D: a posting open to freshers, read as 0-1 years (only when nothing else is stated: the highest minimum wins)
_FRESHER_RE = re.compile(
    r"\b(?:freshers?|fresh\s+graduates?|recent\s+graduates?|new\s+grads?|entry[- ]level|"
    r"no\s+prior\s+(?:work\s+)?experience)\b",
    re.IGNORECASE,
)
# "mentor entry-level engineers", "freshers need not apply"
_FRESHER_NOT_BEFORE_RE = re.compile(r"(?:mentor|coach|manag|lead|train|supervis|guid|onboard|\bnot?\b)\w*\W+(?:\w+\W+){0,2}$",
                                    re.IGNORECASE)
_FRESHER_NOT_AFTER_RE = re.compile(r"^\W*(?:need\s+not|are\s+not|not|ineligible|excluded)\b", re.IGNORECASE)

# Patterns that should NOT be matched — company history, unrelated context
_FALSE_POSITIVE_RE = re.compile(
    r"(?:has been|have been|founded|established|since\s+\d|for over|operating|"
    r"history of|track record of|we.ve been|"
    r"supports? our|in the industry|on the market|"
    r"sentence|imprisonment|prison|warranty|guarantee|screening)",
    re.IGNORECASE,
)
# Text right after the years: "40 years ago", "30 years later", "139 years old", "57 years of unbroken profitability"
_FALSE_POSITIVE_AFTER_RE = re.compile(r"^\W*(?:ago|later|old|young|of\s+(?:unbroken|history|heritage)|(?:of\s+)?full[- ]time\s+education|of\s+education)\b",
                                      re.IGNORECASE)


def _check_match(
    text: str,
    m: re.Match,
    min_years: int,
    max_years: int | None,
) -> bool:
    """Return True if the match looks like a genuine experience requirement."""
    if min_years > 30:
        return False
    if max_years is not None and max_years > 30:
        return False
    if max_years is not None and max_years < min_years:
        return False

    # Check for false positive context in the text preceding the match
    start = max(0, m.start() - 60)
    surrounding = text[start : m.start()]
    if _FALSE_POSITIVE_RE.search(surrounding):
        return False
    return not _FALSE_POSITIVE_AFTER_RE.search(text[_years_end(text, m):][:30])


def _years_end(text: str, m: re.Match) -> int:
    """End of the "N years" words in a match (pattern A matches on into its context)."""
    y = re.compile(r"(?:years?|yrs?|Jahre?n?|ans?|anni?|años?|jaar|år)\.?", re.IGNORECASE).search(text, m.start(), m.end())
    return y.end() if y else m.end()


def extract_experience(html: str) -> ExperienceRequirement | None:
    """Extract years-of-experience requirement from job description HTML.

    Returns the highest stated minimum across all experience mentions,
    or None if no unambiguous requirement is found.
    """
    text = _html_to_text(html)

    best_min: int | None = None
    best_max: int | None = None

    # Pattern A: "N years of ... experience"
    for m in _EXPERIENCE_RE.finditer(text):
        min_years = int(m.group(1))
        max_years = int(m.group(2)) if m.group(2) else None

        if not _check_match(text, m, min_years, max_years):
            continue

        if best_min is None or min_years > best_min:
            best_min = min_years
            best_max = max_years

    # Pattern B: reversed word order ("Erfahrung von 5 Jahren")
    for m in _EXPERIENCE_REVERSED_RE.finditer(text):
        min_years = int(m.group(1))
        max_years = int(m.group(2)) if m.group(2) else None

        if not _check_match(text, m, min_years, max_years):
            continue

        if best_min is None or min_years > best_min:
            best_min = min_years
            best_max = max_years

    # Pattern C: "Experience: 3-5 Years", "Exp- 6+ years"
    for m in _EXPERIENCE_LABEL_RE.finditer(text):
        min_years = int(m.group(1))
        max_years = int(m.group(2)) if m.group(2) else None

        if not _check_match(text, m, min_years, max_years):
            continue

        if best_min is None or min_years > best_min:
            best_min = min_years
            best_max = max_years

    if best_min is None:
        for m in _FRESHER_RE.finditer(text):
            if _FRESHER_NOT_BEFORE_RE.search(text[max(0, m.start() - 40):m.start()]):
                continue
            if _FRESHER_NOT_AFTER_RE.search(text[m.end():m.end() + 20]):
                continue
            return ExperienceRequirement(min_years=0, max_years=1)
        return None

    return ExperienceRequirement(min_years=best_min, max_years=best_max)
