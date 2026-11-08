"""Njoyn (Cegid) job listings, e.g. CGI. Settings: "host" (cgi.njoyn.com), "path" ("/CORP/xweb/xweb.asp"), "clid"."""
import re
from bs4 import BeautifulSoup
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, join_nonempty

KEY_FIELDS = ("host", "clid")
_PAGES = re.compile(r"Page\s+\d+\s+of\s+(\d+)")


def parse_listing(html: str, base: str) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for row in soup.select("tr"):
        link = row.select_one('a[href*="Page=JobDetails"]')
        cells = [c.get_text(" ", strip=True) for c in row.select("td")]
        if not link or len(cells) < 5:
            continue
        job_id, title, category, city, country = cells[:5]
        jobs.append(make_job(
            source_job_id=job_id,
            title=title or link.get_text(" ", strip=True),
            location=join_nonempty([None if city.upper() == "ALL" else city, country], ", "),
            department=category or None,
            apply_url=base.rsplit("/", 1)[0] + "/" + link["href"].lstrip("/"),
        ))
    pages = _PAGES.search(soup.get_text(" "))
    return jobs, int(pages.group(1)) if pages else 1


async def fetch_jobs(http, source: dict) -> FetchResult:
    base = f"https://{source['host']}{source.get('path', '/CORP/xweb/xweb.asp')}"
    url = f"{base}?NTKN=c&clid={source['clid']}&Page=joblisting"
    found: dict[str, dict] = {}
    jobs, pages = parse_listing((await http.request("GET", url)).text, base)
    page = 1
    while True:
        for job in jobs:
            found.setdefault(job["source_job_id"], job)
        page += 1
        if page > pages or len(found) >= settings.max_jobs_per_source:
            break
        # Later pages come from the listing's own search form ("pn" = page number).
        jobs, _ = parse_listing((await http.request("POST", url, data={"pn": str(page)})).text, base)
        if not jobs:
            break
    complete = page > pages
    return FetchResult(valid_jobs(list(found.values())[:settings.max_jobs_per_source]), complete=complete)
