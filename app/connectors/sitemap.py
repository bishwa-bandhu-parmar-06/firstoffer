"""Job boards whose only crawlable listing is the sitemap (robots.txt blocks their search API).

Settings: "sitemap" (URL of a sitemap or sitemap index), optional "job_pattern" (substring that job URLs
contain, default "/job/"), optional "details" (false for sites whose job pages need JavaScript).
Until a job page is read, the title comes from the URL. The sitemap's lastmod is not used as the
posting date: sites regenerate it (Globant marks every job as modified today).
"""
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs
from app.connectors.pages import job_id_from_url, parse_job_page, sitemap_entries, title_from_slug

KEY_FIELDS = ("sitemap",)
# Fields a job page reads more accurately than the sitemap; later listings don't overwrite them.
DETAIL_FIELDS = {"title", "location", "description", "posted_at", "employment_type"}
MAX_SITEMAP_DEPTH = 2


async def _entries(http, url: str, depth: int = 0) -> list[tuple[str, str | None]]:
    children, entries = sitemap_entries((await http.request("GET", url)).text)
    if depth < MAX_SITEMAP_DEPTH:
        for child in children:
            entries.extend(await _entries(http, child, depth + 1))
    return entries


async def fetch_jobs(http, source: dict) -> FetchResult:
    pattern = source.get("job_pattern", "/job/")
    jobs = [
        make_job(
            source_job_id=job_id_from_url(url),
            title=title_from_slug(url),
            apply_url=url,
        )
        for url, _lastmod in await _entries(http, source["sitemap"])
        if pattern in url
    ]
    complete = len(jobs) <= settings.max_jobs_per_source
    return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=complete)


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    if source.get("details", True) is False or not apply_url:
        return {}
    return parse_job_page((await http.request("GET", apply_url)).text)
