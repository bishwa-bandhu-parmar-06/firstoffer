"""SAP SuccessFactors Career Site Builder sites that render search results as HTML (the classic layout).

Settings: "host", optional "search_path" (default "/search/"). Newer Career Site Builder sites render
everything with JavaScript from /services/ (blocked by their robots.txt); use the "sitemap" connector for those.
"""
import re
from bs4 import BeautifulSoup
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs
from app.connectors.pages import job_id_from_url, parse_date, parse_job_page

KEY_FIELDS = ("host",)
DETAIL_FIELDS = {"description", "posted_at"}
_TOTAL = re.compile(r"of\s+([\d,]+)")


def _text(node) -> str | None:
    return node.get_text(" ", strip=True) or None if node else None


def _tile_field(row, name: str) -> str | None:
    # Tile layouts render "<div class='section-field location'><span class='section-label'>Location</span> Pune</div>".
    field = row.select_one(f".section-field.{name}")
    if not field:
        return None
    label = field.select_one(".section-label")
    if label:
        label.extract()
    return _text(field)


def parse_search_page(html: str, host: str) -> tuple[list[dict], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.data-row") or soup.select("li.job-tile")
    jobs = []
    for row in rows:
        link = row.select_one("a.jobTitle-link")
        if not link or not link.get("href"):
            continue
        url = link["href"] if link["href"].startswith("http") else f"https://{host}{link['href']}"
        jobs.append(make_job(
            source_job_id=job_id_from_url(url),
            title=_text(link),
            location=_text(row.select_one(".jobLocation")) or _tile_field(row, "location"),
            department=_text(row.select_one(".jobDepartment")) or _tile_field(row, "department"),
            apply_url=url,
            posted_at=parse_date(_text(row.select_one(".jobDate"))),
        ))
    label = _text(soup.select_one(".paginationLabel"))
    total = _TOTAL.search(label) if label else None
    return jobs, int(total.group(1).replace(",", "")) if total else None


async def fetch_jobs(http, source: dict) -> FetchResult:
    host, path = source["host"], source.get("search_path", "/search/")
    found: dict[str, dict] = {}
    start = 0
    while True:
        html = (await http.request("GET", f"https://{host}{path}", params={"q": "", "startrow": start})).text
        jobs, total = parse_search_page(html, host)
        new = [j for j in jobs if j["source_job_id"] not in found]
        if not new:
            break
        for job in new:
            found[job["source_job_id"]] = job
        start += len(jobs)
        if total is not None and start >= total:
            break
        if len(found) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(list(found.values())[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(list(found.values())))


async def fetch_details(http, source: dict, source_job_id: str, apply_url: str | None = None) -> dict:
    if not apply_url:
        return {}
    page = parse_job_page((await http.request("GET", apply_url)).text)
    return {"description": page.get("description"), "posted_at": page.get("posted_at")}
