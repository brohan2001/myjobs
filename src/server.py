from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.scoring_config import BASE_DIR, SCORE_WEIGHTS
from src.db import create_local_pool, close_all_pools
from src.ranker import matched_skills


def _json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def _json_response(data) -> JSONResponse:
    return JSONResponse(content=json.loads(json.dumps(data, default=_json_default)))

_TEMPLATE_PATH = BASE_DIR / "templates" / "live.html.j2"

_ALL_JOBS = """
SELECT
    jp.id::text,
    jp.titles[1]           AS title,
    jp.source_url          AS url,
    jp.salary_min,
    jp.salary_max,
    jp.salary_currency,
    jp.location_types,
    jp.locations_raw,
    jp.first_seen_at,
    jp.first_seen_at::date::text AS posted_date,
    jp.visa_signal,
    jp.early_career,
    jp.role_category,
    jp.employment_type,
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
WHERE jp.is_active = true
  AND jp.status NOT IN ('applied', 'skipped')
  AND ($3::text = 'all' OR jp.occupation_id = (SELECT id FROM occupation WHERE slug = $3)
       OR jp.occupation_id IN (SELECT id FROM occupation WHERE parent_id = (SELECT id FROM occupation WHERE slug = $3)))
  AND ($4::text = 'all' OR $4 = ANY(jp.location_types))
  AND ($5 = 0 OR jp.salary_min >= $5)
  AND ($6::text = 'all' OR jp.seniority_id = (SELECT id FROM seniority WHERE slug = $6))
  AND ($7::text = 'all' OR jp.employment_type = $7)
ORDER BY jp.first_seen_at DESC
LIMIT $1 OFFSET $2
"""

_TOTAL_JOBS = """
SELECT COUNT(*)
FROM job_posting jp
WHERE jp.is_active = true
  AND jp.status NOT IN ('applied', 'skipped')
  AND ($1::text = 'all' OR jp.occupation_id = (SELECT id FROM occupation WHERE slug = $1)
       OR jp.occupation_id IN (SELECT id FROM occupation WHERE parent_id = (SELECT id FROM occupation WHERE slug = $1)))
  AND ($2::text = 'all' OR $2 = ANY(jp.location_types))
  AND ($3 = 0 OR jp.salary_min >= $3)
  AND ($4::text = 'all' OR jp.seniority_id = (SELECT id FROM seniority WHERE slug = $4))
  AND ($5::text = 'all' OR jp.employment_type = $5)
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
    jp.locations_raw,
    jp.first_seen_at,
    jp.first_seen_at::date::text AS posted_date,
    jp.visa_signal,
    jp.early_career,
    jp.role_category,
    jp.employment_type,
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
WHERE jp.is_active = true
  AND jp.status NOT IN ('applied', 'skipped')
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


_NON_US_TERMS = frozenset([
    "egypt", "cairo", "nigeria", "lagos", "abuja", "india", "bangalore", "bengaluru",
    "mumbai", "delhi", "hyderabad", "pune", "chennai", "kolkata", "gurugram", "noida",
    "pakistan", "karachi", "lahore", "bangladesh", "dhaka", "australia", "sydney",
    "melbourne", "brisbane", "perth", "new zealand", "auckland", "wellington",
    "uk", "united kingdom", "london", "manchester", "birmingham", "edinburgh",
    "germany", "berlin", "munich", "hamburg", "frankfurt", "france", "paris",
    "canada", "toronto", "vancouver", "montreal", "ottawa", "singapore",
    "poland", "warsaw", "krakow", "netherlands", "amsterdam", "spain", "madrid",
    "barcelona", "italy", "milan", "rome", "ireland", "dublin", "south africa",
    "johannesburg", "cape town", "kenya", "nairobi", "israel", "tel aviv",
    "uae", "dubai", "abu dhabi", "japan", "tokyo", "osaka", "china", "beijing",
    "shanghai", "shenzhen", "south korea", "seoul", "brazil", "sao paulo",
    "mexico", "argentina", "buenos aires", "philippines", "manila", "indonesia",
    "jakarta", "vietnam", "ho chi minh", "thailand", "bangkok", "malaysia",
    "kuala lumpur", "sweden", "stockholm", "switzerland", "zurich", "geneva",
    "norway", "oslo", "denmark", "copenhagen", "finland", "helsinki",
    "czech republic", "prague", "romania", "bucharest", "ukraine", "kyiv",
    "russia", "moscow", "turkey", "istanbul", "saudi arabia", "riyadh",
    "hong kong", "taiwan", "taipei", "emea", "apac",
])


def _is_us_strict(locations_raw: list | None) -> bool:
    """True = include in US filter. False = exclude (confirmed non-US location)."""
    if not locations_raw:
        return True  # unknown → include conservatively
    loc_text = " ".join(str(s) for s in locations_raw).lower()
    for term in _NON_US_TERMS:
        if term in loc_text:
            return False
    return True


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/jobs")
async def get_jobs(
    offset: int = 0,
    limit: int = 50,
    role: str = "all",
    work_mode: str = "all",
    salary_min: int = 0,
    location: str = "all",
    level: str = "all",
    employment_type: str = "all",
    company_id: str | None = None,
):
    async with _pool.acquire() as conn:
        if company_id is not None:
            rows = await conn.fetch(_JOBS_BY_COMPANY, company_id)
            total = len(rows)
        else:
            rows = await conn.fetch(_ALL_JOBS, limit, offset, role, work_mode, salary_min, level, employment_type)
            total = await conn.fetchval(_TOTAL_JOBS, role, work_mode, salary_min, level, employment_type)

    result = []
    for row in rows:
        job = _enrich_job(dict(row))
        if location == "us" and not _is_us_strict(job.get("locations_raw")):
            continue
        result.append(job)

    return _json_response({"jobs": result, "total": total})


@app.get("/api/companies")
async def get_companies():
    async with _pool.acquire() as conn:
        rows = await conn.fetch(_COMPANIES_WITH_JOBS)
    return _json_response([dict(r) for r in rows])


@app.post("/api/refresh")
async def trigger_refresh():
    global _pipeline_task
    async with _pipeline_lock:
        if _pipeline_task is not None and not _pipeline_task.done():
            return _json_response({"status": "already_running"})
        from src.cli import _run_pipeline_once
        _pipeline_task = asyncio.create_task(_run_pipeline_once())
    return _json_response({"status": "started"})


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

    return _json_response({
        "status": "running" if running else "idle",
        "task_error": task_error,
        "last_run": dict(last_run) if last_run else None,
        "weights": SCORE_WEIGHTS,
    })
