import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import select
from app.config import settings
from app.connectors import CONNECTORS
from app.db import SessionLocal, init_db
from app.enrich import ENRICH_VERSION, enrich_job, prune_closed_jobs, refresh_groups, source_snapshot
from app.alerts import send_source_alerts
from app.http import Http
from app.models import Job, SourceRun, SourceState, as_utc
from app.sources import load_sources

# Fields where the first known value wins: list pages often only give an approximate date.
KEEP_FIRST_FIELDS = {"posted_at"}
# Give up on detail fetches for a source after this many failures in one run.
MAX_DETAIL_FAILURES = 5
# Jitter so a source polled every 3h is not skipped because the last poll was 2h59m ago.
DUE_SLACK = timedelta(minutes=10)

_poll_lock = asyncio.Lock()


def is_due(source: dict, state: SourceState | None, now: datetime) -> bool:
    if state is None or state.last_attempt_at is None:
        return True
    interval = timedelta(hours=float(source.get("interval_hours", settings.poll_interval_hours)))
    return now - as_utc(state.last_attempt_at) >= interval - DUE_SLACK


def upsert_jobs(db, source: dict, items: list[dict], seeding: bool, now: datetime,
                detail_fields: set[str] = frozenset()) -> tuple[list[Job], set[str]]:
    """Insert new jobs and refresh known ones. Returns (new jobs, ids seen in this listing).

    detail_fields are left alone on jobs whose details were already fetched, since the detail
    call knows them better than the listing (e.g. a real title vs. one guessed from a URL).
    """
    existing = {j.source_job_id: j for j in db.scalars(select(Job).where(Job.source_key == source["key"]))}
    new_jobs, seen = [], set()
    for item in items:
        job_id = item["source_job_id"]
        if job_id in seen:
            continue
        seen.add(job_id)
        job = existing.get(job_id)
        if job is None:
            job = Job(
                **item,
                source_provider=source["provider"],
                source_key=source["key"],
                company=source["company"],
                first_seen_at=now,
                last_seen_at=now,
                active=True,
                # Everything found on a source's first poll is backlog, not news: never announce it.
                notified_at=now if seeding else None,
            )
            enrich_job(job)
            db.add(job)
            new_jobs.append(job)
            continue
        before = source_snapshot(job)
        job.last_seen_at = now
        job.active = True
        job.missed_runs = 0
        job.company = source["company"]
        protected = detail_fields if job.details_fetched_at is not None else frozenset()
        for field, value in item.items():
            if field == "source_job_id" or value is None or field in protected:
                continue
            if field == "description" and not settings.store_descriptions:
                continue
            if field in KEEP_FIRST_FIELDS and getattr(job, field) is not None:
                continue
            setattr(job, field, value)
        if source_snapshot(job) != before or job.enrich_version != ENRICH_VERSION:
            enrich_job(job)
    return new_jobs, seen


def close_missing_jobs(db, source_key: str, seen: set[str]) -> int:
    """Count a miss for active jobs absent from a complete listing; close them after enough misses."""
    closed = 0
    active = db.scalars(select(Job).where(Job.source_key == source_key, Job.active.is_(True)))
    for job in active:
        if job.source_job_id in seen:
            continue
        job.missed_runs += 1
        if job.missed_runs >= settings.missed_runs_before_inactive:
            job.active = False
            closed += 1
    return closed


async def backfill_details(db, http, connector, source: dict, now: datetime) -> int:
    if not hasattr(connector, "fetch_details") or source.get("details", True) is False or settings.detail_fetches_per_run <= 0:
        return 0
    pending = db.scalars(
        select(Job)
        .where(Job.source_key == source["key"], Job.active.is_(True), Job.details_fetched_at.is_(None))
        .order_by(Job.first_seen_at.desc())
        .limit(settings.detail_fetches_per_run)
    ).all()
    # Fetch everything before writing, so no database write is held open across network waits.
    results, failures = {}, 0
    for job in pending:
        try:
            results[job.source_job_id] = await connector.fetch_details(http, source, job.source_job_id, job.apply_url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 410):
                results[job.source_job_id] = {}  # Gone from the source; don't retry forever.
            else:
                failures += 1
        except (httpx.HTTPError, ValueError):
            failures += 1
        if failures >= MAX_DETAIL_FAILURES:
            break
    for job in pending:
        details = results.get(job.source_job_id)
        if details is None:
            continue
        # The detail page is authoritative (e.g. an exact posting date instead of "Posted 3 Days Ago").
        for field, value in details.items():
            if value is not None:
                setattr(job, field, value)
        job.details_fetched_at = now
        enrich_job(job)
    return sum(1 for d in results.values() if d)


async def poll_source(http: Http, source: dict) -> dict:
    connector = CONNECTORS[source["provider"]]
    summary = {"key": source["key"], "company": source["company"], "fetched": 0, "new": 0, "closed": 0, "details": 0, "error": None}
    db = SessionLocal()
    try:
        state = db.get(SourceState, source["key"])
        if state is None:
            state = SourceState(key=source["key"], provider=source["provider"], company=source["company"])
            db.add(state)
        now = datetime.now(timezone.utc)
        state.last_attempt_at = now
        failures_before = state.consecutive_failures or 0
        run = SourceRun(source_key=source["key"], provider=source["provider"], company=source["company"], started_at=now)
        db.add(run)
        db.commit()
        try:
            result = await connector.fetch_jobs(http, source)
            now = datetime.now(timezone.utc)
            seeding = state.seeded_at is None
            new_jobs, seen = upsert_jobs(db, source, result.jobs, seeding, now, getattr(connector, "DETAIL_FIELDS", frozenset()))
            closed = close_missing_jobs(db, source["key"], seen) if result.complete else 0
            if seeding:
                state.seeded_at = now
            state.last_job_count = len(seen)
            state.last_complete = result.complete
            db.commit()
            details = await backfill_details(db, http, connector, source, now)
            run.fetched_count, run.new_count, run.closed_count, run.details_count = len(seen), len(new_jobs), closed, details
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            state.last_success_at = run.finished_at
            state.consecutive_failures = 0
            state.last_error = None
            db.commit()
            # New jobs from later polls keep notified_at empty; app.digest announces them.
            summary.update(fetched=len(seen), new=len(new_jobs), closed=closed, details=details,
                           seeded=seeding, complete=result.complete)
            if failures_before >= settings.alert_after_failures:
                summary["alert"] = "recovered"
        except Exception as exc:
            db.rollback()
            message = f"{type(exc).__name__}: {exc}"[:2000]
            run.status = "error"
            run.error_message = message
            run.finished_at = datetime.now(timezone.utc)
            state.consecutive_failures += 1
            state.last_error = message
            db.add_all([run, state])
            db.commit()
            summary["error"] = message
            if state.consecutive_failures == settings.alert_after_failures:
                summary["alert"] = "failing"
            print(f"ERROR polling {source['company']} ({source['key']}): {message}")
    finally:
        db.close()
    return summary


async def poll_all_sources(force: bool = False, only: str | None = None) -> dict:
    """Poll every enabled source that is due (or all with force=True). `only` filters by company or key substring."""
    if _poll_lock.locked():
        return {"status": "skipped", "reason": "a poll is already running"}
    async with _poll_lock:
        init_db()
        sources = load_sources()
        if only:
            needle = only.lower()
            sources = [s for s in sources if needle in s["company"].lower() or needle in s["key"].lower()]
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            states = {s.key: s for s in db.scalars(select(SourceState))}
        due = [s for s in sources if force or is_due(s, states.get(s["key"]), now)]

        semaphore = asyncio.Semaphore(settings.max_concurrent_sources)
        timeout = httpx.Timeout(settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": settings.user_agent}, follow_redirects=True) as client:
            http = Http(client)

            async def guarded(source):
                async with semaphore:
                    return await poll_source(http, source)

            results = await asyncio.gather(*(guarded(s) for s in due))

        if due:
            with SessionLocal() as db:
                refresh_groups(db)
                pruned = prune_closed_jobs(db, settings.prune_closed_after_days)
            await send_source_alerts([r for r in results if r.get("alert")])

    return {
        "status": "done",
        "sources_configured": len(sources),
        "sources_polled": len(due),
        "fetched": sum(r["fetched"] for r in results),
        "new": sum(r["new"] for r in results),
        "closed": sum(r["closed"] for r in results),
        "errors": sum(1 for r in results if r["error"]),
        "pruned": pruned if due else 0,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Poll configured job sources once.")
    parser.add_argument("--force", action="store_true", help="poll every source, even ones not due yet")
    parser.add_argument("--only", help="only sources whose company or key contains this text")
    args = parser.parse_args()
    totals = asyncio.run(poll_all_sources(force=args.force, only=args.only))
    for r in totals.pop("results", []):
        status = f"ERROR {r['error']}" if r["error"] else (
            f"{r['fetched']} jobs, {r['new']} new, {r['closed']} closed, {r['details']} details"
            + (" (seed run)" if r.get("seeded") else "") + ("" if r.get("complete", True) else " (partial listing)")
        )
        print(f"{r['company']:<32} {status}")
    print(totals)


if __name__ == "__main__":
    main()
