from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso

KEY_FIELDS = ("company_id",)
PAGE_SIZE = 100
API = "https://api.smartrecruiters.com/v1/companies"


def _workplace(location: dict) -> str | None:
    if location.get("remote"):
        return "Remote"
    if location.get("hybrid"):
        return "Hybrid"
    return None


async def fetch_jobs(http, source: dict) -> FetchResult:
    company_id = source["company_id"]
    jobs, offset, total = [], 0, None
    while total is None or offset < total:
        page = await http.get_json(f"{API}/{company_id}/postings", params={"limit": PAGE_SIZE, "offset": offset})
        total = page.get("totalFound") or 0
        content = page.get("content") or []
        if not content:
            break
        for j in content:
            location = j.get("location") or {}
            jobs.append(make_job(
                source_job_id=j.get("id"),
                title=j.get("name"),
                location=location.get("fullLocation") or location.get("city"),
                employment_type=(j.get("typeOfEmployment") or {}).get("label"),
                workplace_type=_workplace(location),
                apply_url=f"https://jobs.smartrecruiters.com/{company_id}/{j.get('id')}",
                department=(j.get("department") or {}).get("label") or (j.get("function") or {}).get("label"),
                posted_at=parse_iso(j.get("releasedDate")),
            ))
        offset += len(content)
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    d = await http.get_json(f"{API}/{source['company_id']}/postings/{source_job_id}")
    sections = (d.get("jobAd") or {}).get("sections") or {}
    parts = []
    for name in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(name) or {}
        if section.get("text"):
            parts.append(f"<h3>{section.get('title', '')}</h3>{section['text']}")
    return {"description": "".join(parts) or None, "apply_url": d.get("postingUrl")}
