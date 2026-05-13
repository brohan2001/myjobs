from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.config import BASE_DIR, SCORE_WEIGHTS
from src.database import (
    get_companies_with_jobs,
    get_conn,
    get_jobs_by_company,
    get_last_run,
    get_shortlisted_jobs,
    init_db,
)
from src.ranker import matched_skills

app = FastAPI(title="myjobs live")

_TEMPLATE_PATH = BASE_DIR / "templates" / "live.html.j2"

_pipeline_task: asyncio.Task | None = None
_pipeline_lock = asyncio.Lock()


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(_TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/jobs")
async def get_jobs(
    days: int = 14,
    us_only: bool = False,
    new_grad_only: bool = False,
    company_id: int | None = None,
    industry: str | None = None,
):
    with get_conn() as conn:
        if company_id is not None:
            rows = get_jobs_by_company(conn, company_id)
        else:
            rows = get_shortlisted_jobs(
                conn,
                days=days,
                us_only=us_only,
                new_grad_only=new_grad_only,
                industry=industry,
            )

    result = []
    for job in rows:
        mk, ms = matched_skills(job.get("description", "") or "")
        job["matched_skills"] = mk[:12]
        job["missing_skills"] = ms[:4]
        job["score_pct"] = int(job.get("total_score", 0))
        job["skill_pts"]   = round(job.get("skill_score",   0) * SCORE_WEIGHTS["skill"],   1)
        job["role_pts"]    = round(job.get("role_score",    0) * SCORE_WEIGHTS["role"],     1)
        job["visa_pts"]    = round(job.get("visa_score",    0) * SCORE_WEIGHTS["visa"],     1)
        job["recency_pts"] = round(job.get("recency_score", 0) * SCORE_WEIGHTS["recency"],  1)
        job["company_pts"] = round(job.get("company_score", 0) * SCORE_WEIGHTS["company"],  1)
        result.append(job)

    return JSONResponse(result)


@app.get("/api/companies")
async def get_companies():
    with get_conn() as conn:
        companies = get_companies_with_jobs(conn)
    return JSONResponse(companies)


@app.post("/api/refresh")
async def trigger_refresh():
    global _pipeline_task
    async with _pipeline_lock:
        if _pipeline_task is not None and not _pipeline_task.done():
            return JSONResponse({"status": "already_running"})
        from src.pipeline import run_daily
        _pipeline_task = asyncio.create_task(run_daily())
    return JSONResponse({"status": "started"})


@app.get("/api/status")
async def get_status():
    running = _pipeline_task is not None and not _pipeline_task.done()

    task_error = None
    if _pipeline_task is not None and _pipeline_task.done():
        exc = _pipeline_task.exception()
        if exc:
            task_error = str(exc)

    with get_conn() as conn:
        last_run = get_last_run(conn)

    return JSONResponse({
        "status": "running" if running else "idle",
        "task_error": task_error,
        "last_run": dict(last_run) if last_run else None,
        "weights": SCORE_WEIGHTS,
    })
