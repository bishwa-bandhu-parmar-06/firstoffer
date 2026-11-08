"""Builds the filtered, de-duplicated job queries behind GET /jobs."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, column, func, or_, select, text
from app.db import IS_SQLITE
from app.models import Job

UNSPECIFIED = "unspecified"
_WORDS = re.compile(r"\w+", re.UNICODE)


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@dataclass
class JobFilters:
    q: str | None = None
    experience: list[str] | None = None
    category: list[str] | None = None
    it_only: bool = False
    company: list[str] | None = None
    country: list[str] | None = None
    city: str | None = None
    remote: bool | None = None
    posted_within_days: int | None = None
    provider: str | None = None
    active: bool = True




def _text_search(q: str):
    words = _WORDS.findall(q)
    if not words:
        return None
    if IS_SQLITE:
        # Every word must match, as a prefix ("devel" finds "Developer"), in title/company/location/department/category.
        expression = " ".join('"' + w.replace('"', "") + '"*' for w in words)
        matches = text("SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :fts").bindparams(fts=expression).columns(column("rowid"))
        return Job.id.in_(matches)
    fields = (Job.title, Job.company, Job.location, Job.department, Job.category)
    return and_(*(or_(*(f.ilike(f"%{w}%") for f in fields)) for w in words))


def conditions(f: JobFilters) -> list:
    conds = [Job.active == f.active]
    if f.q and (search := _text_search(f.q)) is not None:
        conds.append(search)
    if f.experience:
        levels = [e for e in f.experience if e != UNSPECIFIED]
        options = [Job.experience_level.in_(levels)] if levels else []
        if UNSPECIFIED in f.experience:
            options.append(Job.experience_level.is_(None))
        conds.append(or_(*options))
    if f.category:
        conds.append(Job.category.in_(f.category))
    elif f.it_only:
        # Hide only clearly non-IT roles; unclassified jobs stay visible (many are IT roles with vague titles).
        conds.append(or_(Job.category.is_(None), Job.category != "non_it"))
    if f.company:
        conds.append(func.lower(Job.company).in_([c.lower() for c in f.company]))
    if f.country:
        conds.append(or_(*(Job.countries.like(f"%|{c}|%") for c in f.country)))
    if f.city:
        conds.append(Job.city.ilike(f"%{f.city}%"))
    if f.remote is not None:
        conds.append(Job.is_remote == f.remote)
    if f.posted_within_days:
        conds.append(Job.listed_at >= datetime.now(timezone.utc) - timedelta(days=f.posted_within_days))
    if f.provider:
        conds.append(Job.source_provider == f.provider.lower())
    return conds


def job_page(db, f: JobFilters, collapse: bool, sort: str, limit: int, offset: int) -> tuple[int, list[tuple[Job, int]]]:
    """(total results, [(job, number of postings of the same opening)]) for one page.

    With collapse, only each opening's primary posting is returned (see app.enrich.refresh_groups).
    """
    conds = conditions(f)
    if collapse:
        conds.append(Job.is_primary == True)  # noqa: E712 - "= 1" can use the index, "IS 1" can't
    if sort == "first_seen":
        order = (Job.first_seen_at.desc(), Job.id.desc())
    else:  # newest: undated backlog from first polls goes last
        order = (Job.listed_at.desc().nulls_last(), Job.id.desc())
    total = db.scalar(select(func.count(Job.id)).where(*conds))
    jobs = db.scalars(select(Job).where(*conds).order_by(*order).limit(limit).offset(offset)).all()
    return total, [(job, (job.similar_count or 1) if collapse else 1) for job in jobs]
