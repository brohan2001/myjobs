from __future__ import annotations

import re
from datetime import date

from src.scoring_config import (
    INDUSTRY_BONUS,
    RECENCY_BREAKPOINTS,
    ROLE_PRIORITY,
    SCORE_WEIGHTS,
    SKILL_GROUPS,
    TIER_SCORES,
    load_role_keywords,
    load_visa_keywords,
)

_VISA_KW = load_visa_keywords()
_ROLE_KW = load_role_keywords()

_EXP_SENIOR_RE = re.compile(
    r"\b([3-9]|\d{2,})\+?\s*years?\s*(of\s+)?(experience|exp)\b", re.IGNORECASE
)
_EXP_EARLY_RE = re.compile(
    r"\b(entry[\s-]level|junior|new\s+grad|early\s+career|0[\s-]?[–-][\s-]?[12]\s+years?)\b",
    re.IGNORECASE,
)
_SENIOR_TITLE_RE = re.compile(
    r"\b(senior|sr\.|staff|principal|lead|director|head of)\b", re.IGNORECASE
)


def classify_role(title: str | None, description: str) -> str:
    title_lower = (title or "").lower()
    desc_lower = (description or "")[:800].lower()

    # Role priority: more specific roles first (ml/ds/network/cloud/mobile/frontend/backend),
    # then fullstack as catch-all for generic "software engineer" titles.
    priority_order = ["ml", "ds", "network", "cloud", "mobile", "frontend", "backend", "fullstack"]

    # Check title first (stronger signal)
    for role in priority_order:
        for kw in _ROLE_KW.get(role, []):
            if kw in title_lower:
                return role

    # Fall back to description
    for role in priority_order:
        for kw in _ROLE_KW.get(role, []):
            if kw in desc_lower:
                return role

    return "other"


def detect_visa_signal(description: str) -> int:
    """Returns -1 (no sponsorship), 0 (unknown), or 1 (confirmed)."""
    desc_lower = (description or "").lower()
    for phrase in _VISA_KW["negative"]:
        if phrase in desc_lower:
            return -1
    for phrase in _VISA_KW["positive"]:
        if phrase in desc_lower:
            return 1
    return 0


def detect_early_career(title: str | None, description: str) -> int:
    text = ((title or "") + " " + (description or "")[:1000]).lower()
    return 1 if _EXP_EARLY_RE.search(text) else 0


def parse_max_experience(description: str) -> int | None:
    matches = re.findall(r"\b(\d+)\+?\s*years?\s*(of\s+)?(experience|exp)\b",
                         description or "", re.IGNORECASE)
    if not matches:
        return None
    years = [int(m[0]) for m in matches]
    return max(years)


def skill_score(description: str) -> float:
    desc_lower = (description or "").lower()
    matched_w = 0.0
    total_w = 0.0
    for _group, (weight, skills) in SKILL_GROUPS.items():
        for skill in skills:
            total_w += weight
            if skill in desc_lower:
                matched_w += weight
    if total_w == 0:
        return 0.0
    raw = matched_w / total_w
    # Multiplier tuned so matching ~20% of candidate skills → full score
    # (a job mentioning ~15 of our 75 skills is an excellent match)
    return min(1.0, raw * 5.0)


def role_score(role_category: str) -> float:
    return ROLE_PRIORITY.get(role_category, 0.20)


def visa_score(visa_signal: int) -> float:
    if visa_signal == -1:
        return 0.0
    if visa_signal == 1:
        return 1.0
    return 0.4


def recency_score(posted_date) -> float:
    if not posted_date:
        return 0.3
    try:
        if isinstance(posted_date, date):
            d = posted_date
        else:
            d = date.fromisoformat(str(posted_date)[:10])
    except ValueError:
        return 0.3
    days_old = (date.today() - d).days
    for threshold, score in reversed(RECENCY_BREAKPOINTS):
        if days_old >= threshold:
            return score
    return RECENCY_BREAKPOINTS[-1][1]


def company_score(tier: int, industry: str) -> float:
    base = TIER_SCORES.get(tier, 0.35)
    bonus = INDUSTRY_BONUS.get(industry or "", 0.0)
    return min(1.0, base + bonus)


def is_senior_role(title: str | None, description: str, exp_years_max: int | None) -> bool:
    if _SENIOR_TITLE_RE.search(title or ""):
        return True
    if exp_years_max is not None and exp_years_max >= 3:
        if not _EXP_EARLY_RE.search(description or ""):
            return True
    return False


def score_job(job: dict) -> dict:
    """
    Returns a dict of all sub-scores and total_score (out of 100).
    job must have: description, role_category, visa_signal, posted_date, tier, industry.
    """
    sk = skill_score(job.get("description", ""))
    ro = role_score(job.get("role_category", "other"))
    vi = visa_score(job.get("visa_signal", 0))
    re_ = recency_score(job.get("posted_date"))
    co = company_score(job.get("tier", 2), job.get("industry", ""))

    total = (
        sk  * SCORE_WEIGHTS["skill"]   +
        ro  * SCORE_WEIGHTS["role"]    +
        vi  * SCORE_WEIGHTS["visa"]    +
        re_ * SCORE_WEIGHTS["recency"] +
        co  * SCORE_WEIGHTS["company"]
    )

    # Early-career penalty for senior-looking roles
    if is_senior_role(
        job.get("title", ""),
        job.get("description", ""),
        job.get("exp_years_max"),
    ):
        total *= 0.35

    return {
        "skill_score":   round(sk,   4),
        "role_score":    round(ro,   4),
        "visa_score":    round(vi,   4),
        "recency_score": round(re_,  4),
        "company_score": round(co,   4),
        "total_score":   round(total, 4),
    }


def parse_signals(job: dict) -> dict:
    """Extract visa_signal, early_career, role_category, exp_years_max from a job dict."""
    desc = job.get("description", "")
    title = job.get("title", "")
    # Prefer the normalize step's pre-populated value when available (uses
    # jobseek's higher-precision extract_experience). Fall back to the simpler
    # parse_max_experience regex for jobs that entered the DB via other paths.
    exp_years = job.get("exp_years_max")
    if exp_years is None:
        exp_years = parse_max_experience(desc)
    return {
        "visa_signal":   detect_visa_signal(desc),
        "early_career":  detect_early_career(title, desc),
        "role_category": classify_role(title, desc),
        "exp_years_max": exp_years,
    }


_FETCH_JOBS_FOR_SCORING = """
SELECT jp.id,
       jp.titles[1]             AS title,
       jp.first_seen_at::date   AS posted_date,
       jp.experience_max        AS exp_years_max,
       c.tier,
       d.html                   AS description
FROM job_posting jp
JOIN company c ON c.id = jp.company_id
LEFT JOIN descriptions d ON d.posting_id = jp.id
WHERE jp.is_active = true
  AND jp.status NOT IN ('applied', 'skipped')
ORDER BY jp.id
"""

_UPDATE_SCORES = """
UPDATE job_posting SET
    visa_signal   = $2,
    early_career  = $3,
    role_category = $4,
    skill_score   = $5,
    role_score    = $6,
    visa_score    = $7,
    recency_score = $8,
    company_score = $9,
    total_score   = $10
WHERE id = $1
"""

_MARK_SHORTLISTED = """
UPDATE job_posting SET status = 'shortlisted'
WHERE id = ANY($1::uuid[])
"""

_RESET_SHORTLISTED = """
UPDATE job_posting SET status = 'new'
WHERE status = 'shortlisted'
  AND is_active = true
"""


async def run_scoring(pool, shortlist_top: int = 50) -> int:
    """Score all active postings, shortlist top-N. Returns count shortlisted."""
    from bs4 import BeautifulSoup

    def _strip_html(html: str | None) -> str:
        if not html:
            return ""
        return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)

    async with pool.acquire() as conn:
        rows = await conn.fetch(_FETCH_JOBS_FOR_SCORING)

    score_updates: list[tuple] = []
    job_scores: list[tuple[float, str]] = []

    for row in rows:
        job = dict(row)
        job["description"] = _strip_html(job.get("description"))
        signals = parse_signals(job)
        job.update(signals)
        scores = score_job(job)
        score_updates.append((
            job["id"],
            signals["visa_signal"],
            signals["early_career"],
            signals["role_category"],
            scores["skill_score"],
            scores["role_score"],
            scores["visa_score"],
            scores["recency_score"],
            scores["company_score"],
            scores["total_score"],
        ))
        if signals["visa_signal"] != -1:
            job_scores.append((scores["total_score"], str(job["id"])))

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(_UPDATE_SCORES, score_updates)
            await conn.execute(_RESET_SHORTLISTED)
            top_ids = [jid for _, jid in sorted(job_scores, reverse=True)[:shortlist_top]]
            if top_ids:
                await conn.execute(_MARK_SHORTLISTED, top_ids)

    return len(top_ids) if top_ids else 0


def matched_skills(description: str) -> tuple[list[str], list[str]]:
    """Returns (matched_skills, missing_skills) for top skills from description."""
    desc_lower = (description or "").lower()
    matched = []
    missing = []
    # Focus on languages + frameworks for display (most meaningful)
    for group in ("languages", "frameworks", "cloud", "ml"):
        _, skills = SKILL_GROUPS[group]
        for skill in skills:
            if skill in desc_lower:
                matched.append(skill)
            else:
                missing.append(skill)
    return matched[:10], missing[:6]
