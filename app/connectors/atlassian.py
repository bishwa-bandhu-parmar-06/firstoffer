"""Atlassian's careers listing JSON (one request returns every job). Settings: "host"."""
from datetime import datetime, timezone
from app.connectors.base import FetchResult, make_job, valid_jobs, join_nonempty

KEY_FIELDS = ("host",)


def _updated(value: str | None) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d %I:%M %p").replace(tzinfo=timezone.utc) if value else None
    except ValueError:
        return None


async def fetch_jobs(http, source: dict) -> FetchResult:
    raw = await http.get_json(f"https://{source['host']}/endpoint/careers/listings")
    jobs = []
    for j in raw:
        portal = j.get("portalJobPost") or {}
        sections = [(None, j.get("overview")), ("Responsibilities", j.get("responsibilities")),
                    ("Qualifications", j.get("qualifications"))]
        description = "".join(f"<h3>{label}</h3>{text}" if label else text for label, text in sections if text)
        jobs.append(make_job(
            source_job_id=j.get("id"),
            title=j.get("title"),
            # Locations look like "Bengaluru - India -   Bengaluru,  560071 India"; keep the "City - Country" part.
            location=join_nonempty(" - ".join(p.strip() for p in loc.split(" - ")[:2]) for loc in j.get("locations") or []),
            employment_type=j.get("type"),
            description=description or None,
            apply_url=portal.get("portalUrl") or j.get("applyUrl"),
            department=j.get("category"),
            posted_at=_updated(portal.get("updatedDate")),
        ))
    return FetchResult(valid_jobs(jobs))
