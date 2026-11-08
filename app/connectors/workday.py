import re
from datetime import datetime, timedelta, timezone
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, parse_iso, join_nonempty

KEY_FIELDS = ("host", "tenant", "site")
DETAIL_FIELDS = {"location", "posted_at"}
PAGE_SIZE = 20  # Workday rejects larger pages.
# Workday never reports more than 2000 results for one search (and wraps around past it),
# so bigger boards are split into several searches using the board's own filters (facets).
RESULT_CAP = 2000
MAX_SPLIT_DEPTH = 2

_DAYS_AGO = re.compile(r"(\d+)\s+Days?\s+Ago", re.I)


def _base(source: dict) -> str:
    return f"https://{source['host']}/wday/cxs/{source['tenant']}/{source['site']}"


def parse_posted_on(text: str | None, now: datetime | None = None) -> datetime | None:
    """Turn 'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' into a date. '30+ Days Ago' is unknown."""
    if not text or "+" in text:
        return None
    today = (now or datetime.now(timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
    lowered = text.lower()
    if "today" in lowered:
        return today
    if "yesterday" in lowered:
        return today - timedelta(days=1)
    match = _DAYS_AGO.search(text)
    return today - timedelta(days=int(match.group(1))) if match else None


def leaf_facets(facets: list[dict]) -> list[tuple[str, list[dict]]]:
    """Flatten Workday facets (some, like locationMainGroup, nest other facets) into (parameter, values)."""
    leaves = []
    for facet in facets or []:
        values = facet.get("values") or []
        nested = [v for v in values if "facetParameter" in v]
        if nested:
            leaves.extend(leaf_facets(nested))
        elif facet.get("facetParameter") and values:
            leaves.append((facet["facetParameter"], values))
    return leaves


def pick_split_facet(facets: list[dict], applied: dict) -> tuple[str, list[dict]] | None:
    candidates = [
        (param, values) for param, values in leaf_facets(facets)
        if param not in applied and len(values) > 1 and all(v.get("id") for v in values)
    ]
    if not candidates:
        return None

    def counts(values):
        return [v.get("count") or 0 for v in values]

    under_cap = [c for c in candidates if max(counts(c[1])) < RESULT_CAP]
    if under_cap:
        # Among filters that cover at least the capped total, take the one needing the fewest searches.
        # (Location filters often have 100+ values, while job category has ~15.)
        covering = [c for c in under_cap if sum(counts(c[1])) >= RESULT_CAP]
        if covering:
            return min(covering, key=lambda c: len(c[1]))
        return max(under_cap, key=lambda c: sum(counts(c[1])))
    return min(candidates, key=lambda c: max(counts(c[1])))


async def fetch_jobs(http, source: dict) -> FetchResult:
    url = _base(source) + "/jobs"
    found: dict[str, dict] = {}
    complete = True

    def collect(postings):
        for p in postings:
            path = p.get("externalPath")
            if path and path not in found:
                found[path] = make_job(
                    source_job_id=path,
                    title=p.get("title"),
                    location=p.get("locationsText"),
                    apply_url=f"https://{source['host']}/{source['site']}{path}",
                    posted_at=parse_posted_on(p.get("postedOn")),
                )

    def body(applied, offset):
        return {"appliedFacets": applied, "limit": PAGE_SIZE, "offset": offset, "searchText": ""}

    async def search(applied: dict, depth: int):
        nonlocal complete
        first = await http.post_json(url, json=body(applied, 0))
        # Only the first page carries the real total; later pages report 0.
        total = first.get("total") or 0
        if total >= RESULT_CAP and depth < MAX_SPLIT_DEPTH:
            split = pick_split_facet(first.get("facets") or [], applied)
            if split:
                param, values = split
                for value in values:
                    if len(found) >= settings.max_jobs_per_source:
                        complete = False
                        return
                    await search({**applied, param: [value["id"]]}, depth + 1)
                return
        if total >= RESULT_CAP:
            complete = False
        collect(first.get("jobPostings") or [])
        offset = PAGE_SIZE
        while offset < min(total, RESULT_CAP):
            if len(found) >= settings.max_jobs_per_source:
                complete = False
                return
            postings = (await http.post_json(url, json=body(applied, offset))).get("jobPostings") or []
            if not postings:
                break
            collect(postings)
            offset += PAGE_SIZE

    await search({}, 0)
    return FetchResult(valid_jobs(list(found.values())[:settings.max_jobs_per_source]), complete=complete)


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    info = (await http.get_json(_base(source) + source_job_id)).get("jobPostingInfo") or {}
    return {
        # The list says "3 Locations" for multi-location jobs; the detail names them.
        "location": join_nonempty([info.get("location")] + list(info.get("additionalLocations") or [])),
        "description": info.get("jobDescription"),
        "employment_type": info.get("timeType"),
        "workplace_type": info.get("remoteType"),
        "posted_at": parse_iso(info.get("startDate")),
        "apply_url": info.get("externalUrl"),
    }
