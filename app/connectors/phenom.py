"""Phenom People career sites, via the /widgets search endpoint the site's own search page calls.

Settings: "host", "lang" (e.g. "en_global"), "country" (e.g. "global"), "job_url_prefix" (e.g. "/global/en").
"""
import re
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso

KEY_FIELDS = ("host", "lang")
PAGE_SIZE = 50


def _slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-") or "job"


async def fetch_jobs(http, source: dict) -> FetchResult:
    host, prefix = source["host"], source.get("job_url_prefix", "")
    jobs, start, total = [], 0, None
    while total is None or start < total:
        data = await http.post_json(f"https://{host}/widgets", json={
            "lang": source["lang"], "deviceType": "desktop", "country": source.get("country", "global"),
            "pageName": "search-results", "ddoKey": "refineSearch", "from": start, "jobs": True, "counts": True,
            "size": PAGE_SIZE, "siteType": "external", "global": True, "selected_fields": {},
            "sort": {"order": "desc", "field": "postedDate"},
        })
        search = data.get("refineSearch") or {}
        total = search.get("totalHits") or 0
        batch = (search.get("data") or {}).get("jobs") or []
        if not batch:
            break
        for j in batch:
            job_id = j.get("jobId") or j.get("reqId")
            jobs.append(make_job(
                source_job_id=job_id,
                title=j.get("title"),
                location=j.get("location") or j.get("cityStateCountry"),
                description=j.get("descriptionTeaser"),
                # The feed's applyUrl can point at a staging system; link the public job page instead.
                apply_url=f"https://{host}{prefix}/job/{job_id}/{_slug(j.get('title'))}" if job_id else None,
                department=j.get("category"),
                posted_at=parse_iso(j.get("postedDate")),
            ))
        start += len(batch)
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))
