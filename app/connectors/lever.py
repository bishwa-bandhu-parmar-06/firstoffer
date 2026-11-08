from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, from_epoch

KEY_FIELDS = ("site",)


def _description(j: dict) -> str | None:
    parts = [j.get("description") or ""]
    for section in j.get("lists") or []:
        parts.append(f"<h3>{section.get('text', '')}</h3><ul>{section.get('content', '')}</ul>")
    parts.append(j.get("additional") or "")
    text = "".join(parts).strip()
    return text or j.get("descriptionPlain")


async def fetch_jobs(http, source: dict) -> FetchResult:
    raw = await http.get_json(f"https://api.lever.co/v0/postings/{source['site']}", params={"mode": "json"})
    jobs = []
    for j in raw[:settings.max_jobs_per_source]:
        categories = j.get("categories") or {}
        all_locations = categories.get("allLocations")
        jobs.append(make_job(
            source_job_id=j.get("id"),
            title=j.get("text"),
            location=categories.get("location") or (", ".join(all_locations) if isinstance(all_locations, list) else all_locations),
            employment_type=categories.get("commitment"),
            workplace_type=j.get("workplaceType") or categories.get("workplaceType"),
            description=_description(j),
            apply_url=j.get("hostedUrl") or j.get("applyUrl"),
            department=categories.get("team") or categories.get("department"),
            # Lever sends createdAt as epoch milliseconds.
            posted_at=from_epoch(j.get("createdAt"), millis=True),
        ))
    return FetchResult(valid_jobs(jobs), complete=len(raw) <= settings.max_jobs_per_source)
