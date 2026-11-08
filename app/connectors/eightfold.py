from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, from_epoch, join_nonempty

# "api" picks the Eightfold API generation: "pcsx" (newer, default) or "v2".
KEY_FIELDS = ("host", "domain")
PAGE_SIZE = 10  # Eightfold returns at most 10 positions per page.


def _locations(p: dict) -> str | None:
    locations = p.get("locations") or p.get("standardizedLocations")
    if isinstance(locations, list) and locations:
        return join_nonempty(locations)
    return p.get("location")


def _pcsx_job(source: dict, p: dict) -> dict:
    return make_job(
        source_job_id=p.get("id"),
        title=p.get("name"),
        location=_locations(p),
        workplace_type=p.get("workLocationOption"),
        apply_url=f"https://{source['host']}{p['positionUrl']}" if p.get("positionUrl") else None,
        department=p.get("department"),
        posted_at=from_epoch(p.get("postedTs") or p.get("creationTs")),
    )


def _v2_job(source: dict, p: dict) -> dict:
    return make_job(
        source_job_id=p.get("id"),
        title=p.get("name") or p.get("posting_name"),
        location=_locations(p),
        workplace_type=p.get("work_location_option"),
        description=p.get("job_description") or None,
        apply_url=p.get("canonicalPositionUrl") or f"https://{source['host']}/careers/job/{p.get('id')}",
        department=p.get("department"),
        posted_at=from_epoch(p.get("t_create")),
    )


async def fetch_jobs(http, source: dict) -> FetchResult:
    pcsx = source.get("api", "pcsx") == "pcsx"
    path = "/api/pcsx/search" if pcsx else "/api/apply/v2/jobs"
    jobs, start, total = [], 0, None
    while total is None or start < total:
        params = {"domain": source["domain"], "start": start, "num": PAGE_SIZE}
        if pcsx:
            params["query"] = ""
        page = await http.get_json(f"https://{source['host']}{path}", params=params)
        data = (page.get("data") or {}) if pcsx else page
        total = data.get("count") or 0
        positions = data.get("positions") or []
        if not positions:
            break
        jobs.extend((_pcsx_job if pcsx else _v2_job)(source, p) for p in positions)
        start += len(positions)
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    if source.get("api", "pcsx") == "pcsx":
        page = await http.get_json(
            f"https://{source['host']}/api/pcsx/position_details",
            params={"position_id": source_job_id, "domain": source["domain"], "hl": "en"},
        )
        data = page.get("data") or {}
        return {"description": data.get("jobDescription"), "apply_url": data.get("publicUrl")}
    data = await http.get_json(f"https://{source['host']}/api/apply/v2/jobs/{source_job_id}", params={"domain": source["domain"]})
    return {"description": data.get("job_description") or None}
