"""Derive experience level, category, location fields and a duplicate key for each job.

The poller calls enrich_job() whenever a job is new or its source fields change. Run
`python -m app.enrich` to (re)compute every job, e.g. after changing the rules here or in
app.classify / app.locations (bump ENRICH_VERSION so the poller also picks the change up).
"""
import argparse
import hashlib
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import String, cast, delete, func, or_, select, text, update
from app.config import settings
from app.classify import classify_category, classify_experience
from app.db import SessionLocal, init_db
from app.locations import parse_location
from app.models import Job, SourceRun, as_utc

ENRICH_VERSION = 3
# Source fields the derived fields depend on.
SOURCE_FIELDS = ("title", "description", "location", "workplace_type", "department", "company")
# In lite storage descriptions aren't kept, so a listing that repeats one is not a change.
LITE_SOURCE_FIELDS = tuple(f for f in SOURCE_FIELDS if f != "description")

_REQ_SUFFIX = re.compile(r"\s*[\(\[]?\b(req|job|jr|r)\s*#?\s*[-:]?\s*\d+[\)\]]?\s*$", re.I)
_NON_WORD = re.compile(r"[^\w]+")


def normalize_title(title: str) -> str:
    return _NON_WORD.sub(" ", _REQ_SUFFIX.sub("", title or "").lower()).strip()


def dedup_key(company: str, title: str, place: str | None) -> str:
    raw = "|".join([(company or "").strip().lower(), normalize_title(title), (place or "").strip().lower()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def enrich_job(job: Job) -> None:
    level, years = classify_experience(job.title, job.description)
    place = parse_location(job.location, job.workplace_type)
    job.experience_level = level
    job.experience_years = years
    job.category = classify_category(job.title, job.department)
    job.city = place.city
    job.country = place.country
    job.countries = "|" + "|".join(place.countries) + "|" if place.countries else None
    job.is_remote = place.is_remote
    job.dedup_key = dedup_key(job.company, job.title, place.city or place.country)
    job.listed_at = job.posted_at or (None if _from_seed_run(job) else job.first_seen_at)
    job.enrich_version = ENRICH_VERSION
    if not settings.store_descriptions:
        job.description = None  # lite storage: used above for the experience level, then dropped


def _from_seed_run(job: Job) -> bool:
    # Seed-run jobs are marked notified at the moment they are first stored.
    first, notified = as_utc(job.first_seen_at), as_utc(job.notified_at)
    return first is not None and notified is not None and abs((notified - first).total_seconds()) < 1


def refresh_groups(db) -> None:
    """Pick one primary posting per dedup group among active jobs and record each group's size."""
    group = func.coalesce(Job.dedup_key, cast(Job.id, String))
    ranked = select(
        Job.id,
        func.min(Job.id).over(partition_by=group).label("primary_id"),
        func.count(Job.id).over(partition_by=group).label("size"),
    ).where(Job.active.is_(True)).subquery()
    # Only touch rows whose values change: rewriting every row on each poll is costly on hosted Postgres.
    db.execute(update(Job).where(
        Job.id == ranked.c.id,
        or_(Job.is_primary.is_distinct_from(Job.id == ranked.c.primary_id), Job.similar_count.is_distinct_from(ranked.c.size)),
    ).values(is_primary=(Job.id == ranked.c.primary_id), similar_count=ranked.c.size))
    db.execute(update(Job).where(Job.active.is_(False), or_(Job.is_primary.is_(None), Job.is_primary.is_(True)))
               .values(is_primary=False, similar_count=None))
    db.commit()
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("PRAGMA optimize"))  # refreshes planner statistics when the data has shifted


def source_snapshot(job: Job) -> tuple:
    return tuple(getattr(job, f) for f in (SOURCE_FIELDS if settings.store_descriptions else LITE_SOURCE_FIELDS))


def prune_closed_jobs(db, days: int) -> int:
    """Delete jobs that closed more than `days` days ago, and run logs of the same age."""
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = db.execute(delete(Job).where(Job.active.is_(False), Job.last_seen_at < cutoff)).rowcount
    db.execute(delete(SourceRun).where(SourceRun.started_at < cutoff))
    db.commit()
    return removed or 0


def enrich_all(only_stale: bool = True, batch_size: int = 2000) -> int:
    init_db()
    done, last_id = 0, 0
    while True:
        with SessionLocal() as db:
            stmt = select(Job).where(Job.id > last_id).order_by(Job.id).limit(batch_size)
            if only_stale:
                stmt = stmt.where(or_(Job.enrich_version.is_(None), Job.enrich_version != ENRICH_VERSION))
            jobs = db.scalars(stmt).all()
            if not jobs:
                refresh_groups(db)
                return done
            for job in jobs:
                enrich_job(job)
            db.commit()
            done += len(jobs)
            last_id = jobs[-1].id
            print(f"enriched {done} jobs")


def main():
    parser = argparse.ArgumentParser(description="Compute experience level, category and location fields for stored jobs.")
    parser.add_argument("--all", action="store_true", help="recompute every job, not only ones from older rule versions")
    args = parser.parse_args()
    print(f"done: {enrich_all(only_stale=not args.all)} jobs")


if __name__ == "__main__":
    main()
