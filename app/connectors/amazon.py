"""amazon.jobs search JSON. Settings: "host" (www.amazon.jobs).

Like Workday, a single search stops at 10,000 results, so the listing is split by country and,
for countries above the cap (the US), by business category.
"""
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs
from app.connectors.pages import parse_date

KEY_FIELDS = ("host",)
PAGE_SIZE = 100
RESULT_CAP = 10000


def _facet(data: dict, name: str) -> list[tuple[str, int]]:
    # Facets come back as [{"USA": 12792}, {"IND": 2186}, ...].
    return [(k, v) for entry in (data.get("facets") or {}).get(f"{name}_facet", []) for k, v in entry.items()]


def _job(host: str, j: dict) -> dict:
    description = "".join(
        f"<h3>{label}</h3><p>{j[key]}</p>" if label else f"<p>{j[key]}</p>"
        for key, label in (("description", None), ("basic_qualifications", "Basic qualifications"),
                           ("preferred_qualifications", "Preferred qualifications"))
        if j.get(key)
    )
    return make_job(
        source_job_id=j.get("id_icims") or j.get("id"),
        title=j.get("title"),
        location=j.get("normalized_location") or j.get("location"),
        employment_type=j.get("job_schedule_type"),
        description=description or None,
        apply_url=f"https://{host}{j['job_path']}" if j.get("job_path") else None,
        department=j.get("job_category"),
        posted_at=parse_date(j.get("posted_date")),
    )


async def fetch_jobs(http, source: dict) -> FetchResult:
    host = source["host"]
    url = f"https://{host}/en/search.json"
    found: dict[str, dict] = {}
    complete = True

    async def search(filters: dict, facets: list[str] = ()) -> dict:
        return await http.get_json(url, params={**filters, "result_limit": PAGE_SIZE if not facets else 1,
                                                "offset": 0, **({"facets[]": list(facets)} if facets else {})})

    async def collect(filters: dict, hits: int):
        offset = 0
        while offset < min(hits, RESULT_CAP) and len(found) < settings.max_jobs_per_source:
            data = await http.get_json(url, params={**filters, "result_limit": PAGE_SIZE, "offset": offset})
            batch = data.get("jobs") or []
            if not batch:
                break
            for j in batch:
                job = _job(host, j)
                found.setdefault(job["source_job_id"], job)
            offset += PAGE_SIZE

    countries = _facet(await search({}, ["normalized_country_code"]), "normalized_country_code")
    for country, count in countries:
        filters = {"normalized_country_code[]": country}
        if count < RESULT_CAP:
            await collect(filters, count)
            continue
        for category, category_count in _facet(await search(filters, ["business_category"]), "business_category"):
            if category_count >= RESULT_CAP:
                complete = False
            await collect({**filters, "business_category[]": category}, category_count)
    if len(found) >= settings.max_jobs_per_source:
        complete = False
    return FetchResult(valid_jobs(list(found.values())[:settings.max_jobs_per_source]), complete=complete)
