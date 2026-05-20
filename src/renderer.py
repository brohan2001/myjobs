from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from src.scoring_config import BASE_DIR, OUTPUT_DIR, SCORE_WEIGHTS
from src.ranker import matched_skills

_TEMPLATES_DIR = BASE_DIR / "templates"

_FETCH_SHORTLIST = """
SELECT
    jp.id,
    jp.titles[1]           AS title,
    jp.source_url          AS url,
    jp.salary_min,
    jp.salary_max,
    jp.salary_currency,
    jp.location_types,
    jp.first_seen_at::date AS posted_date,
    jp.visa_signal,
    jp.early_career,
    jp.role_category,
    jp.skill_score,
    jp.role_score,
    jp.visa_score,
    jp.recency_score,
    jp.company_score,
    jp.total_score,
    jp.status,
    jp.applied_at,
    c.name AS company_name,
    c.tier,
    d.html AS description_html
FROM job_posting jp
JOIN company c ON c.id = jp.company_id
LEFT JOIN descriptions d ON d.posting_id = jp.id AND d.locale = 'en'
WHERE jp.status = 'shortlisted'
  AND jp.is_active = true
ORDER BY jp.total_score DESC
LIMIT $1
"""


def _visa_label(signal: int) -> str:
    if signal == 1:
        return "CONFIRMED"
    if signal == -1:
        return "NO SPONSOR"
    return "UNCONFIRMED"


def _visa_class(signal: int) -> str:
    if signal == 1:
        return "visa-yes"
    if signal == -1:
        return "visa-no"
    return "visa-unknown"


def _role_badge_class(role: str) -> str:
    mapping = {
        "backend": "role-backend", "cloud": "role-cloud",
        "fullstack": "role-fullstack", "frontend": "role-frontend",
        "mobile": "role-mobile", "network": "role-network",
        "ds": "role-ds", "ml": "role-ml",
    }
    return mapping.get(role, "role-other")


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


async def fetch_shortlist(pool, limit: int = 50) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_FETCH_SHORTLIST, limit)
    result = []
    for row in rows:
        job = dict(row)
        job["description"] = _strip_html(job.pop("description_html", None))
        location_types = job.get("location_types") or []
        job["location"] = ", ".join(location_types) if location_types else ""
        result.append(job)
    return result


def render_report(
    shortlist: list[dict],
    run_date: str,
    stats: dict,
) -> Path:
    output_dir = OUTPUT_DIR / run_date
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.html"

    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    env.globals["visa_label"] = _visa_label
    env.globals["visa_class"] = _visa_class
    env.globals["role_badge_class"] = _role_badge_class

    jobs_data = []
    for job in shortlist:
        mk, ms = matched_skills(job.get("description", ""))
        job["matched_skills"] = mk
        job["missing_skills"] = ms[:4]
        job["score_pct"] = int(job.get("total_score", 0))
        job["skill_pts"]   = round(job.get("skill_score",   0) * SCORE_WEIGHTS["skill"],   1)
        job["role_pts"]    = round(job.get("role_score",    0) * SCORE_WEIGHTS["role"],     1)
        job["visa_pts"]    = round(job.get("visa_score",    0) * SCORE_WEIGHTS["visa"],     1)
        job["recency_pts"] = round(job.get("recency_score", 0) * SCORE_WEIGHTS["recency"],  1)
        job["company_pts"] = round(job.get("company_score", 0) * SCORE_WEIGHTS["company"],  1)
        jobs_data.append(job)

    stats.setdefault("elapsed_s", 0)
    stats.setdefault("jobs_scraped", 0)
    stats.setdefault("jobs_new", 0)
    stats.setdefault("shortlisted", len(jobs_data))
    stats.setdefault("errors", 0)

    template = env.get_template("daily_report.html.j2")
    html = template.render(
        jobs=jobs_data,
        run_date=run_date,
        stats=stats,
        weights=SCORE_WEIGHTS,
    )
    report_path.write_text(html, encoding="utf-8")
    return report_path
