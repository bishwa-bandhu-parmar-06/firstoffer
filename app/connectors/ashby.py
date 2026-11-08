from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso, join_nonempty

KEY_FIELDS = ("org",)


async def fetch_jobs(http, source: dict) -> FetchResult:
    data = await http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{source['org']}")
    raw = [j for j in data.get("jobs", []) if j.get("isListed", True)]
    jobs = [
        make_job(
            source_job_id=j.get("id"),
            title=j.get("title"),
            location=join_nonempty([j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]),
            employment_type=j.get("employmentType"),
            workplace_type=j.get("workplaceType") or ("Remote" if j.get("isRemote") else None),
            description=j.get("descriptionHtml") or j.get("descriptionPlain"),
            apply_url=j.get("jobUrl") or j.get("applyUrl"),
            department=join_nonempty([j.get("department"), j.get("team")], " / "),
            posted_at=parse_iso(j.get("publishedAt")),
        )
        for j in raw[:settings.max_jobs_per_source]
    ]
    return FetchResult(valid_jobs(jobs), complete=len(raw) <= settings.max_jobs_per_source)
