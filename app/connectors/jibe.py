"""iCIMS Jibe career sites (e.g. careers.amd.com): JSON at /api/jobs.

Settings: "host", optional "job_path" (public job page, default "/careers-home/jobs/{slug}").
"""
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso

KEY_FIELDS = ("host",)
PAGE_SIZE = 100


def _job(source: dict, d: dict) -> dict:
    job_path = source.get("job_path", "/careers-home/jobs/{slug}")
    description = "".join(d.get(name) or "" for name in ("description", "responsibilities", "qualifications"))
    categories = d.get("categories") or []
    return make_job(
        source_job_id=d.get("req_id") or d.get("slug"),
        title=d.get("title"),
        location=d.get("full_location") or d.get("location_name"),
        employment_type=(d.get("employment_type") or "").replace("_", " ").title() or None,
        description=description or None,
        apply_url=f"https://{source['host']}{job_path.format(slug=d.get('slug'))}" if d.get("slug") else d.get("apply_url"),
        department=d.get("department") or (categories[0].get("name") if categories and isinstance(categories[0], dict) else None),
        posted_at=parse_iso(d.get("posted_date") or d.get("create_date")),
    )


async def fetch_jobs(http, source: dict) -> FetchResult:
    jobs, page, total = [], 1, None
    while total is None or len(jobs) < total:
        data = await http.get_json(f"https://{source['host']}/api/jobs", params={"limit": PAGE_SIZE, "page": page})
        total = data.get("totalCount") or 0
        batch = data.get("jobs") or []
        if not batch:
            break
        jobs.extend(_job(source, j.get("data", j)) for j in batch)
        page += 1
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))
