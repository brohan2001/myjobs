from __future__ import annotations

import sqlite3
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.config import BASE_DIR, OUTPUT_DIR, SCORE_WEIGHTS
from src.ranker import matched_skills

_TEMPLATES_DIR = BASE_DIR / "templates"


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


def _score_bar(score: float, max_score: float) -> str:
    pct = int((score / max_score) * 100) if max_score else 0
    return f"{pct}%"


def _role_badge_class(role: str) -> str:
    mapping = {
        "backend": "role-backend", "cloud": "role-cloud",
        "fullstack": "role-fullstack", "frontend": "role-frontend",
        "mobile": "role-mobile", "network": "role-network",
        "ds": "role-ds", "ml": "role-ml",
    }
    return mapping.get(role, "role-other")


def render_report(
    shortlist: list[sqlite3.Row],
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
    for row in shortlist:
        job = dict(row)
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

    template = env.get_template("daily_report.html.j2")
    html = template.render(
        jobs=jobs_data,
        run_date=run_date,
        stats=stats,
        weights=SCORE_WEIGHTS,
    )
    report_path.write_text(html, encoding="utf-8")
    return report_path
