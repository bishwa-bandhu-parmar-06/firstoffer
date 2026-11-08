"""Helpers for connectors that read HTML job pages and sitemaps instead of JSON APIs."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup
from app.connectors.base import parse_iso, join_nonempty

# Site-name suffixes some careers sites add to <title>.
_TITLE_SUFFIXES = (
    re.compile(r"\s*Job Details\s*\|.*$", re.I),
    re.compile(r"(\s*-\s*)+\d+\s*$"),  # Avature: "Data Analyst -  - 48752"
    re.compile(r"\s*\|\s*[^|]*$"),
)
_ID_AT_END = re.compile(r"/(\d+)/?$")
_URL_ENTRY = re.compile(r"<url>(.*?)</url>", re.S)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_LASTMOD = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>")


def job_id_from_url(url: str) -> str:
    match = _ID_AT_END.search(urlsplit(url).path)
    return match.group(1) if match else url


def title_from_slug(url: str) -> str | None:
    """Best-effort title from a job URL like /job/Senior-Data-Engineer/1234/ (used until the page is read)."""
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    if not parts:
        return None
    slug = unquote(parts[-1])
    if "-" not in slug and " " not in slug:
        slug = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", slug)  # "BusinessAnalyst" -> "Business Analyst"
    return re.sub(r"\s+", " ", slug.replace("-", " ")).strip() or None


def parse_date(value: str | None, formats=("%b %d, %Y", "%B %d, %Y", "%B %d,%Y", "%Y-%m-%d")) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return parse_iso(value)


def sitemap_entries(xml: str) -> tuple[list[str], list[tuple[str, str | None]]]:
    """Return (child sitemap URLs, [(page URL, lastmod)]) from a sitemap or sitemap index."""
    if "<sitemapindex" in xml:
        return _LOC.findall(xml), []
    entries = []
    for block in _URL_ENTRY.findall(xml):
        loc = _LOC.search(block)
        if loc:
            lastmod = _LASTMOD.search(block)
            entries.append((loc.group(1).replace("&amp;", "&"), lastmod.group(1) if lastmod else None))
    return [], entries


def _clean_title(title: str | None) -> str | None:
    if not title:
        return None
    title = re.sub(r"\s+", " ", title).strip()
    for pattern in _TITLE_SUFFIXES:
        cleaned = pattern.sub("", title).strip()
        if cleaned:
            title = cleaned
    return title or None


def _ld_location(value) -> str | None:
    places = value if isinstance(value, list) else [value]
    names = []
    for place in places:
        if not isinstance(place, dict):
            continue
        address = place.get("address") or {}
        if isinstance(address, dict):
            names.append(join_nonempty([address.get("addressLocality"), address.get("addressRegion"),
                                        address.get("addressCountry") if isinstance(address.get("addressCountry"), str) else None], ", "))
    return join_nonempty(names)


def parse_job_page(html: str) -> dict:
    """Pull title/description/date/location from a job page: schema.org JSON-LD, then itemprop markup, then <title>."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                employment = item.get("employmentType")
                return {
                    "title": _clean_title(item.get("title")),
                    "description": item.get("description") or None,
                    "posted_at": parse_iso(item.get("datePosted")),
                    "location": _ld_location(item.get("jobLocation")),
                    "employment_type": ", ".join(employment) if isinstance(employment, list) else employment,
                }

    result = {}
    title = soup.select_one('[itemprop="title"]')
    description = soup.select_one('[itemprop="description"]')
    date_posted = soup.select_one('[itemprop="datePosted"]')
    location = soup.select_one(".jobGeoLocation") or soup.select_one('[itemprop="jobLocation"]')
    if title:
        result["title"] = _clean_title(title.get("content") or title.get_text(" ", strip=True))
    if description:
        result["description"] = description.decode_contents().strip() or None
    if date_posted:
        result["posted_at"] = parse_date(date_posted.get("content") or date_posted.get_text(strip=True))
    if location:
        result["location"] = location.get_text(" ", strip=True) or None
    if not result.get("title"):
        og = soup.select_one('meta[property="og:title"]')
        page_title = soup.title.get_text() if soup.title else None
        result["title"] = _clean_title(page_title) or _clean_title(og.get("content") if og else None)
    return result
