from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.scoring_config import BASE_DIR, SCORE_WEIGHTS
from src.db import create_local_pool, close_all_pools
from src.ranker import matched_skills

_TEMPLATE_PATH = BASE_DIR / "templates" / "live.html.j2"

_SHORTLISTED_JOBS = """
SELECT
    jp.id::text,
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
    jp.board_id::text,
    c.id::text             AS company_id,
    c.name                 AS company_name,
    c.tier,
    d.html                 AS description_html
FROM job_posting jp
JOIN company c ON c.id = jp.company_id
LEFT JOIN descriptions d ON d.posting_id = jp.id AND d.locale = 'en'
WHERE jp.status = 'shortlisted'
  AND jp.is_active = true
  AND jp.first_seen_at >= now() - ($1 || ' days')::interval
ORDER BY jp.total_score DESC
"""

_JOBS_BY_COMPANY = """
SELECT
    jp.id::text,
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
    c.id::text             AS company_id,
    c.name                 AS company_name,
    c.tier,
    d.html                 AS description_html
FROM job_posting jp
JOIN company c ON c.id = jp.company_id
LEFT JOIN descriptions d ON d.posting_id = jp.id AND d.locale = 'en'
WHERE jp.company_id = $1::uuid
  AND jp.status NOT IN ('applied', 'skipped')
  AND jp.is_active = true
ORDER BY jp.first_seen_at DESC
LIMIT 50
"""

_COMPANIES_WITH_JOBS = """
SELECT c.id::text, c.name, c.tier, c.slug, COUNT(jp.id) AS job_count
FROM company c
JOIN job_posting jp ON jp.company_id = c.id
WHERE jp.status = 'shortlisted'
  AND jp.is_active = true
GROUP BY c.id, c.name, c.tier, c.slug
ORDER BY c.tier ASC, job_count DESC
"""

_LAST_RUN = """
SELECT * FROM daily_runs ORDER BY started_at DESC LIMIT 1
"""


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


def _enrich_job(job: dict) -> dict:
    job["description"] = _strip_html(job.pop("description_html", None))
    location_types = job.get("location_types") or []
    job["location"] = ", ".join(location_types) if location_types else ""
    mk, ms = matched_skills(job.get("description", "") or "")
    job["matched_skills"] = mk[:12]
    job["missing_skills"] = ms[:4]
    job["score_pct"] = int(job.get("total_score", 0))
    job["skill_pts"]   = round(job.get("skill_score",   0) * SCORE_WEIGHTS["skill"],   1)
    job["role_pts"]    = round(job.get("role_score",    0) * SCORE_WEIGHTS["role"],     1)
    job["visa_pts"]    = round(job.get("visa_score",    0) * SCORE_WEIGHTS["visa"],     1)
    job["recency_pts"] = round(job.get("recency_score", 0) * SCORE_WEIGHTS["recency"],  1)
    job["company_pts"] = round(job.get("company_score", 0) * SCORE_WEIGHTS["company"],  1)
    return job


_pool = None
_pipeline_task: asyncio.Task | None = None
_pipeline_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await create_local_pool()
    yield
    await close_all_pools()


app = FastAPI(title="myjobs live", lifespan=lifespan)


def _is_us(location: str) -> bool:
    if not location:
        return True
    loc_l = location.lower()
    non_us = {"india", "canada", "united kingdom", "ireland", "germany", "australia",
               "singapore", "poland", "netherlands", "france", "spain", "brazil"}
    for s in non_us:
        if s in loc_l:
            return False
    return True


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/jobs")
async def get_jobs(
    days: int = 14,
    us_only: bool = False,
    new_grad_only: bool = False,
    company_id: str | None = None,
):
    async with _pool.acquire() as conn:
        if company_id is not None:
            rows = await conn.fetch(_JOBS_BY_COMPANY, company_id)
        else:
            rows = await conn.fetch(_SHORTLISTED_JOBS, str(days))

    result = []
    for row in rows:
        job = _enrich_job(dict(row))
        if us_only and not _is_us(job.get("location", "")):
            continue
        if new_grad_only and not (job.get("early_career") or job.get("exp_years_max") is None):
            continue
        result.append(job)

    return JSONResponse(result, default=str)


@app.get("/api/companies")
async def get_companies():
    async with _pool.acquire() as conn:
        rows = await conn.fetch(_COMPANIES_WITH_JOBS)
    return JSONResponse([dict(r) for r in rows], default=str)


@app.post("/api/refresh")
async def trigger_refresh():
    global _pipeline_task
    async with _pipeline_lock:
        if _pipeline_task is not None and not _pipeline_task.done():
            return JSONResponse({"status": "already_running"})
        from src.cli import _run_pipeline_once
        _pipeline_task = asyncio.create_task(_run_pipeline_once())
    return JSONResponse({"status": "started"})


@app.get("/api/status")
async def get_status():
    running = _pipeline_task is not None and not _pipeline_task.done()

    task_error = None
    if _pipeline_task is not None and _pipeline_task.done():
        exc = _pipeline_task.exception()
        if exc:
            task_error = str(exc)

    async with _pool.acquire() as conn:
        last_run = await conn.fetchrow(_LAST_RUN)

    return JSONResponse({
        "status": "running" if running else "idle",
        "task_error": task_error,
        "last_run": dict(last_run) if last_run else None,
        "weights": SCORE_WEIGHTS,
    }, default=str)
