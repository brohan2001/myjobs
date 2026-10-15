"""Public, read-only feed API (FastAPI).

Everyone sees the same feed: the latest jobs from every tracked career board.
No auth, because nothing here is user data; abuse is bounded by per-IP rate
limits, capped page sizes, keyset pagination and the DB statement timeout.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

import nh3
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api import queries
from src.api.locations import LocationIndex, load_location_index
from src.api.ratelimit import RateLimiter
from src.config import settings
from src.logger import get_logger

log = get_logger(__name__)


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_job(row, index: LocationIndex) -> dict:
    ids = row["location_ids"] or []
    types = row["location_types"] or []
    locations = []
    for i, loc_id in enumerate(ids):
        loc_type = types[i] if i < len(types) else None
        if loc_id is None:
            locations.append({"id": None, "name": "Remote", "country": None, "type": loc_type})
            continue
        locations.append({
            "id": loc_id,
            "name": index.label(loc_id) if index.loaded else None,
            "country": index.country_code(loc_id) if index.loaded else None,
            "type": loc_type,
        })
    salary = None
    if row["salary_min"] or row["salary_max"]:
        salary = {
            "min": row["salary_min"],
            "max": row["salary_max"],
            "currency": row["salary_currency"],
            "period": row["salary_period"],
        }
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "url": row["url"],
        "company": {
            "slug": row["company_slug"],
            "name": row["company_name"],
            "website": row["company_website"],
            "logo": row["company_logo"],
            "type": row.get("company_type"),
        },
        "locations": locations,
        "locations_raw": list(row["locations_raw"] or []),
        "work_modes": sorted({t for t in types if t}),
        "employment_type": row["employment_type"],
        "experience": (
            {"min_years": row["experience_min"], "max_years": row["experience_max"]}
            if row.get("experience_min") is not None or row.get("experience_max") is not None
            else None
        ),
        "salary": salary,
        "ats": row["ats"],
        "listed_at": _iso(row["listed_at"]),
        "posted_at": _iso(row.get("posted_at")),
        "first_seen_at": _iso(row["first_seen_at"]),
        "last_seen_at": _iso(row["last_seen_at"]),
    }


def sanitize_description(html: str | None) -> str | None:
    """Third-party HTML → safe subset (no scripts, styles, event handlers or iframes)."""
    if not html:
        return None
    return nh3.clean(html, link_rel="noopener noreferrer nofollow")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db import close_all_pools, create_local_pool

    pool = await create_local_pool()
    app.state.pool = pool
    try:
        app.state.locations = await load_location_index(pool)
    except Exception:  # noqa: BLE001 - feed still works without location labels
        log.warning("api.locations.unavailable", exc_info=True)
        app.state.locations = LocationIndex()

    redis_client = None
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url, socket_timeout=0.5)
        await redis_client.ping()
    except Exception:  # noqa: BLE001
        log.warning("api.ratelimit.local_only")
        redis_client = None
    app.state.limiter = RateLimiter(settings.api_rate_limit_per_minute, redis=redis_client)
    try:
        yield
    finally:
        if redis_client is not None:
            await redis_client.aclose()
        await close_all_pools()


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title="myjobs feed",
        version="1",
        lifespan=lifespan if use_lifespan else None,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    origins = [o.strip() for o in settings.api_cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET"],
            allow_headers=["*"],
            max_age=600,
        )

    @app.middleware("http")
    async def rate_limit_and_headers(request: Request, call_next):
        limiter: RateLimiter | None = getattr(request.app.state, "limiter", None)
        if limiter is not None and request.url.path.startswith("/api/v1/"):
            client = request.client.host if request.client else "unknown"
            allowed, remaining, reset_in = await limiter.hit(client)
            if not allowed:
                return JSONResponse(
                    {"detail": "Too many requests. Slow down a little."},
                    status_code=429,
                    headers={"Retry-After": str(reset_in), **_SECURITY_HEADERS},
                )
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    @app.get("/api/v1/jobs")
    async def list_jobs(
        request: Request,
        q: str | None = Query(None, max_length=100, description="Search title or company"),
        country: str | None = Query(None, max_length=8, description="ISO-3166 alpha-2 (IN, US) or macro (EU, APAC)"),
        location: int | None = Query(None, description="GeoNames id of a city/region/country"),
        company: str | None = Query(None, max_length=100, description="Company slug"),
        work_mode: str | None = Query(None, description="remote | hybrid | onsite"),
        since: str | None = Query(None, max_length=40, description="24h, 7d or ISO-8601"),
        seniority: str | None = Query(None, max_length=50),
        occupation: str | None = Query(None, max_length=80),
        max_years: int | None = Query(None, ge=0, le=40, description="Minimum experience required is at most this many years"),
        company_type: str | None = Query(None, max_length=80, description="Comma-separated: " + ", ".join(queries.COMPANY_TYPES)),
        cursor: str | None = Query(None, max_length=200),
        limit: int = Query(50, ge=1, le=queries.MAX_LIMIT),
    ):
        index: LocationIndex = request.app.state.locations
        try:
            location_ids = None
            if location is not None:
                location_ids = tuple(index.descendants(location)) if index.loaded else (location,)
            elif country:
                ids = index.ids_for_code(country) if index.loaded else None
                if ids is None:
                    raise queries.InvalidFilter(f"unknown country or region code: {country}")
                location_ids = tuple(ids)
            filters = queries.JobFilters(
                q=q.strip() if q and q.strip() else None,
                location_ids=location_ids,
                company=company,
                work_mode=work_mode,
                since=queries.parse_since(since),
                seniority=seniority,
                occupation=occupation,
                max_years=max_years,
                company_types=tuple(t.strip() for t in company_type.split(",") if t.strip()) if company_type else None,
                cursor=queries.decode_cursor(cursor),
                limit=limit,
            )
            rows, next_cursor = await queries.fetch_jobs(request.app.state.pool, filters)
        except queries.InvalidFilter as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {"jobs": [serialize_job(r, index) for r in rows], "next_cursor": next_cursor},
            headers={"Cache-Control": "public, max-age=30"},
        )

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(request: Request, job_id: UUID):
        row = await queries.fetch_job(request.app.state.pool, job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        job = serialize_job(row, request.app.state.locations)
        job["is_active"] = row["is_active"]
        job["description_html"] = sanitize_description(row["description_html"])
        return JSONResponse(job, headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/v1/companies")
    async def list_companies(
        request: Request,
        q: str | None = Query(None, max_length=100),
        limit: int = Query(100, ge=1, le=500),
    ):
        rows = await queries.fetch_companies(request.app.state.pool, q, limit)
        return JSONResponse(
            {"companies": [
                {**{k: r[k] for k in ("slug", "name", "website", "logo", "active_jobs")},
                 "latest_job_at": _iso(r["latest_job_at"])}
                for r in rows
            ]},
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get("/api/v1/locations")
    async def search_locations(request: Request, q: str = Query(..., min_length=1, max_length=60)):
        index: LocationIndex = request.app.state.locations
        return {"locations": [
            {"id": i, "name": index.label(i), "type": index.types[i],
             "code": next((c for c, v in index.codes.items() if v == i), None)
                     if index.types[i] in ("country", "macro") else None}
            for i in index.search(q)
        ]}

    @app.get("/api/v1/stats")
    async def stats(request: Request):
        s = await queries.fetch_stats(request.app.state.pool)
        s["last_updated"] = _iso(s.get("last_updated"))
        return JSONResponse(s, headers={"Cache-Control": "public, max-age=30"})

    @app.get("/api/v1/coverage")
    async def coverage(request: Request):
        """Which sources the feed covers and how healthy they are."""
        data = await queries.fetch_coverage(request.app.state.pool)
        for row in data["by_ats"]:
            row["last_success_at"] = _iso(row.get("last_success_at"))
        return JSONResponse(data, headers={"Cache-Control": "public, max-age=300"})

    return app


app = create_app()
