import html
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso, join_nonempty

KEY_FIELDS = ("board_token",)


async def fetch_jobs(http, source: dict) -> FetchResult:
    url = f"https://boards-api.greenhouse.io/v1/boards/{source['board_token']}/jobs"
    raw = (await http.get_json(url, params={"content": "true"})).get("jobs", [])
    jobs = [
        make_job(
            source_job_id=j.get("id"),
            title=j.get("title"),
            location=(j.get("location") or {}).get("name"),
            # Greenhouse returns the HTML entity-escaped, e.g. "&lt;p&gt;".
            description=html.unescape(j["content"]) if j.get("content") else None,
            apply_url=j.get("absolute_url"),
            department=join_nonempty((d.get("name") for d in j.get("departments") or []), ", "),
            posted_at=parse_iso(j.get("first_published") or j.get("updated_at")),
        )
        for j in raw[:settings.max_jobs_per_source]
    ]
    return FetchResult(valid_jobs(jobs), complete=len(raw) <= settings.max_jobs_per_source)
