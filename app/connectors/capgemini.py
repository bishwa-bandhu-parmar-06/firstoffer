"""Capgemini's job index at /wp-json/llm/v1/jobs (explicitly allowed in its robots.txt). Settings: "host"."""
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso, join_nonempty

KEY_FIELDS = ("host",)
PAGE_SIZE = 50  # the API's maximum


def _country(code: str | None) -> str | None:
    # country_code is a locale like "en-in" or "es-mx".
    return code.split("-")[-1].upper() if code else None


async def fetch_jobs(http, source: dict) -> FetchResult:
    url = f"https://{source['host']}/wp-json/llm/v1/jobs"
    jobs, page, pages = [], 1, None
    while pages is None or page <= pages:
        data = await http.get_json(url, params={"page": page, "size": PAGE_SIZE})
        pages = data.get("total_pages") or 0
        items = data.get("items") or []
        if not items:
            break
        for j in items:
            jobs.append(make_job(
                source_job_id=j.get("id"),
                title=j.get("title"),
                location=join_nonempty([j.get("location"), _country(j.get("country_code"))], ", "),
                employment_type=j.get("contract_type") or None,
                apply_url=j.get("html_url"),
                department=j.get("department") or None,
            ))
        page += 1
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    d = await http.get_json(f"https://{source['host']}/wp-json/llm/v1/jobs/{source_job_id}")
    content = d.get("content")
    level = d.get("experience_level")
    return {
        "description": (f"<p><strong>Experience level:</strong> {level}</p>" if level else "")
                       + (f"<div style=\"white-space: pre-line\">{content}</div>" if content else "") or None,
        "department": d.get("department") or d.get("business_unit") or None,
        "posted_at": parse_iso(d.get("date_published")),
    }
