import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db import SessionLocal, init_db
from app.models import Job, SourceState
from app.config import settings
from app.digest import run_digest
from app.poller import poll_all_sources
from app.sources import load_link_only, load_sources
from app.classify import CATEGORY_LABELS, EXPERIENCE_LABELS, EXPERIENCE_LEVELS, IT_CATEGORIES
from app.search import UNSPECIFIED, JobFilters, job_page, split_list
from app.share import DASHBOARD_DIR, public_base_url, render_job_page, robots_txt, sitemap_xml

scheduler = AsyncIOScheduler(timezone="UTC")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Each tick polls only the sources that are due, so different sources can have different intervals.
    scheduler.add_job(poll_all_sources, "interval", minutes=max(1, settings.scheduler_tick_minutes),
                      id="poll-due-sources", replace_existing=True, max_instances=1, coalesce=True)
    if settings.telegram_bot_token and settings.telegram_chat_id:
        scheduler.add_job(run_digest, "cron", minute=settings.digest_minute % 60,
                          id="telegram-digest", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()
    # Computing filter counts takes a few seconds on a large database; do it before the first visitor asks.
    asyncio.get_running_loop().run_in_executor(None, _warm_filter_cache)
    yield
    scheduler.shutdown(wait=False)

def _warm_filter_cache():
    with SessionLocal() as db:
        for it_only in (False, True):
            filter_options(it_only, db)

app = FastAPI(title="FirstOffer API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["GET"], allow_headers=["*"])

@app.middleware("http")
async def revalidate_pages(request: Request, call_next):
    """Browsers must re-check HTML pages, so visitors get the new dashboard right after a deploy.
    (Built assets have content hashes in their names, so they can still be cached.)"""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_admin(x_admin_token: str | None = Header(default=None)):
    if not settings.admin_token:
        raise HTTPException(403, "Admin endpoints are disabled: set ADMIN_TOKEN in .env")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(401, "Missing or wrong X-Admin-Token header")

@app.get("/health")
def health():
    return {"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}

@app.post("/admin/poll", dependencies=[Depends(require_admin)])
async def manual_poll(force: bool = False, only: str | None = None):
    return await poll_all_sources(force=force, only=only)

def job_summary(j: Job, similar: int = 1) -> dict:
    return {
        "id": j.id, "company": j.company, "title": j.title, "location": j.location,
        "city": j.city, "country": j.country, "is_remote": j.is_remote,
        "experience_level": j.experience_level, "experience_years": j.experience_years,
        "category": j.category, "employment_type": j.employment_type, "workplace_type": j.workplace_type,
        "department": j.department, "apply_url": j.apply_url, "posted_at": j.posted_at,
        "first_seen_at": j.first_seen_at, "source_provider": j.source_provider, "similar_count": similar,
    }

@app.post("/admin/digest", dependencies=[Depends(require_admin)])
async def manual_digest(dry_run: bool = True):
    """Preview (default) or send the Telegram digest now."""
    return await run_digest(dry_run=dry_run)

@app.get("/jobs")
def list_jobs(
    q: str | None = Query(None, description="Words to find in title, company, location, department or category"),
    experience: str | None = Query(None, description=f"Comma list of {', '.join(EXPERIENCE_LEVELS)}, unspecified"),
    category: str | None = Query(None, description=f"Comma list of {', '.join(CATEGORY_LABELS)}"),
    it_only: bool = Query(False, description="Hide clearly non-IT jobs (ignored when category is given)"),
    company: str | None = Query(None, description="Comma list of exact company names"),
    country: str | None = Query(None, description="Comma list of country names, e.g. India,United States"),
    city: str | None = None,
    remote: bool | None = None,
    posted_within_days: int | None = Query(None, ge=1),
    provider: str | None = None,
    active: bool = True,
    collapse: bool = Query(True, description="Show re-posts of the same opening as one result"),
    sort: str = Query("newest", pattern="^(newest|first_seen)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = JobFilters(
        q=q, experience=split_list(experience), category=split_list(category), it_only=it_only,
        company=split_list(company), country=split_list(country), city=city, remote=remote,
        posted_within_days=posted_within_days, provider=provider, active=active,
    )
    total, rows = job_page(db, filters, collapse, sort, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "items": [job_summary(j, n) for j, n in rows]}

@app.get("/jobs/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    similar = []
    if job.dedup_key:
        similar = db.scalars(select(Job).where(Job.dedup_key == job.dedup_key, Job.id != job.id, Job.active == True).limit(20)).all()
    return {
        **job_summary(job, len(similar) + 1),
        "description": job.description, "active": job.active, "last_seen_at": job.last_seen_at,
        "similar_postings": [{"id": s.id, "location": s.location, "apply_url": s.apply_url} for s in similar],
    }

_filters_cache: dict[bool, tuple[float, dict]] = {}
FILTERS_CACHE_SECONDS = 600

@app.get("/filters")
def filter_options(it_only: bool = False, db: Session = Depends(get_db)):
    """Values and open-job counts for the dashboard's filter menus (cached for 10 minutes)."""
    cached = _filters_cache.get(it_only)
    if cached and time.monotonic() - cached[0] < FILTERS_CACHE_SECONDS:
        return cached[1]
    _filters_cache[it_only] = (time.monotonic(), _compute_filter_options(it_only, db))
    return _filters_cache[it_only][1]

def _compute_filter_options(it_only: bool, db: Session) -> dict:
    base = [Job.active == True]
    if it_only:
        base.append(Job.category != "non_it")

    def counts(col, limit=None):
        stmt = select(col, func.count(Job.id)).where(*base).group_by(col).order_by(func.count(Job.id).desc())
        return db.execute(stmt.limit(limit) if limit else stmt).all()

    experience = dict(counts(Job.experience_level))
    categories = dict(counts(Job.category))
    return {
        "experience": [{"value": v, "label": EXPERIENCE_LABELS[v], "count": experience.get(v, 0)} for v in EXPERIENCE_LEVELS]
                      + [{"value": UNSPECIFIED, "label": "Not specified", "count": experience.get(None, 0)}],
        "categories": [{"value": v, "label": label, "count": categories.get(v, 0), "is_it": v in IT_CATEGORIES}
                       for v, label in CATEGORY_LABELS.items()],
        "countries": [{"value": v, "count": n} for v, n in counts(Job.country, 100) if v],
        "companies": [{"value": v, "count": n} for v, n in counts(Job.company)],
        "remote_count": db.scalar(select(func.count(Job.id)).where(*base, Job.is_remote == True)),
    }

@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Job.id)))
    active = db.scalar(select(func.count(Job.id)).where(Job.active == True))
    companies = db.scalar(select(func.count(func.distinct(Job.company))).where(Job.active == True))
    return {"total_jobs": total, "active_jobs": active, "companies_with_jobs": companies}

@app.get("/companies")
def companies(db: Session = Depends(get_db)):
    """Every tracked company: ones we collect jobs from (with open-job counts) and link-only ones."""
    counts = dict(db.execute(select(Job.company, func.count(Job.id)).where(Job.active == True).group_by(Job.company)).all())
    collected = sorted({s["company"] for s in load_sources()})
    return {
        "collected": [{"company": c, "active_jobs": counts.get(c, 0)} for c in collected],
        "link_only": load_link_only(),
    }

@app.get("/sources")
def source_health(db: Session = Depends(get_db)):
    """Health of each polled source, failing ones first."""
    states = db.scalars(select(SourceState).order_by(desc(SourceState.consecutive_failures), SourceState.company)).all()
    return [{
        "key": s.key, "company": s.company, "provider": s.provider,
        "last_success_at": s.last_success_at, "last_attempt_at": s.last_attempt_at,
        "last_job_count": s.last_job_count, "complete_listing": s.last_complete,
        "consecutive_failures": s.consecutive_failures, "last_error": s.last_error,
    } for s in states]

@app.get("/site")
def site_info():
    """Public settings the dashboard needs: brand name and Telegram channel link."""
    return {"brand_name": settings.brand_name, "telegram_channel_url": settings.telegram_channel_url or None}

@app.get("/job/{job_id}", response_class=HTMLResponse, include_in_schema=False)
def job_share_page(job_id: int, request: Request, db: Session = Depends(get_db)):
    """The page behind a shared job link: the dashboard, with a link preview describing this job."""
    job = db.get(Job, job_id)
    page = render_job_page(job, public_base_url(str(request.base_url)))
    return HTMLResponse(page, status_code=200 if job else 404)

@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots(request: Request):
    return robots_txt(public_base_url(str(request.base_url)))

_sitemap_cache: tuple[float, str] | None = None

@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request, db: Session = Depends(get_db)):
    global _sitemap_cache
    if _sitemap_cache is None or time.monotonic() - _sitemap_cache[0] > FILTERS_CACHE_SECONDS:
        rows = db.execute(select(Job.id, Job.last_seen_at)
                          .where(Job.active == True, Job.is_primary == True)  # noqa: E712
                          .order_by(Job.listed_at.desc().nulls_last()).limit(49_999)).all()
        _sitemap_cache = (time.monotonic(), sitemap_xml(public_base_url(str(request.base_url)), [tuple(r) for r in rows]))
    return Response(_sitemap_cache[1], media_type="application/xml")

# The built React dashboard (cd dashboard && npm run build). Mounted last so the API routes above win.
if DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
