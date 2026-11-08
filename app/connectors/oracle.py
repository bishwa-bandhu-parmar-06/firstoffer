from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso, join_nonempty

# Oracle HCM Candidate Experience. "public_host" (optional) is the branded careers domain used in apply links.
KEY_FIELDS = ("host", "site")
PAGE_SIZE = 200


def _api(source: dict, resource: str) -> str:
    return f"https://{source['host']}/hcmRestApi/resources/latest/{resource}"


async def fetch_jobs(http, source: dict) -> FetchResult:
    site = source["site"]
    public_host = source.get("public_host") or source["host"]
    jobs, offset, total = [], 0, None
    while total is None or offset < total:
        data = await http.get_json(_api(source, "recruitingCEJobRequisitions"), params={
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": f"findReqs;siteNumber={site},limit={PAGE_SIZE},offset={offset},sortBy=POSTING_DATES_DESC",
        })
        items = data.get("items") or [{}]
        total = items[0].get("TotalJobsCount") or 0
        reqs = items[0].get("requisitionList") or []
        if not reqs:
            break
        for r in reqs:
            secondary = [s.get("Name") for s in r.get("secondaryLocations") or []]
            jobs.append(make_job(
                source_job_id=r.get("Id"),
                title=r.get("Title"),
                location=join_nonempty([r.get("PrimaryLocation")] + secondary),
                workplace_type=r.get("WorkplaceType"),
                description=r.get("ShortDescriptionStr"),
                apply_url=f"https://{public_host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r.get('Id')}",
                department=r.get("JobFamily") or r.get("Department"),
                posted_at=parse_iso(r.get("PostedDate")),
            ))
        offset += len(reqs)
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    data = await http.get_json(_api(source, "recruitingCEJobRequisitionDetails"), params={
        "onlyData": "true",
        "expand": "all",
        "finder": f'ById;Id="{source_job_id}",siteNumber={source["site"]}',
    })
    d = (data.get("items") or [{}])[0]
    description = "".join(
        d.get(name) or "" for name in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")
    )
    return {
        "description": description or None,
        "employment_type": d.get("JobSchedule"),
        "department": d.get("Category"),
        "posted_at": parse_iso(d.get("ExternalPostedStartDate")),
    }
