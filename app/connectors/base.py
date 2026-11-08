import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Fields every connector returns per job. Missing values are None; the poller fills in
# source_provider, source_key and company.
JOB_FIELDS = (
    "source_job_id", "title", "location", "employment_type", "workplace_type",
    "description", "apply_url", "department", "posted_at",
)


@dataclass
class FetchResult:
    jobs: list[dict] = field(default_factory=list)
    # False when the listing was cut short (result caps, max_jobs_per_source). Jobs missing
    # from an incomplete listing are not counted towards closing them.
    complete: bool = True


def make_job(**values) -> dict:
    unknown = set(values) - set(JOB_FIELDS)
    if unknown:
        raise ValueError(f"Unknown job fields: {sorted(unknown)}")
    job = {name: values.get(name) for name in JOB_FIELDS}
    job["source_job_id"] = str(job["source_job_id"]) if job["source_job_id"] is not None else None
    job["title"] = re.sub(r"\s+", " ", job["title"] or "").strip() or "Untitled role"
    return job


def valid_jobs(jobs: list[dict]) -> list[dict]:
    return [j for j in jobs if j["source_job_id"] and j["apply_url"]]


def parse_iso(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def from_epoch(value, millis: bool = False) -> datetime | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000 if millis else value, tz=timezone.utc)


def join_nonempty(values, sep: str = "; ") -> str | None:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return sep.join(seen) or None
