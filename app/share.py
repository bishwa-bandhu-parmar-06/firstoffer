"""Server-side pieces of the public site: link previews for shared job pages, sitemap and robots.txt.

The dashboard is a single-page app, so a shared link like /job/123 would otherwise show the same
generic preview everywhere. Here the dashboard's index.html gets job-specific <title>, Open Graph
and Twitter tags (used by WhatsApp, Telegram, LinkedIn, X...) plus schema.org JobPosting data
(used by Google's job search) before it is sent.
"""
import html
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from app.config import settings
from app.models import Job, as_utc

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r" ([.,;:!?)])")
_TITLE = re.compile(r"<title>.*?</title>", re.S)
# The home page's generic description and Open Graph tags; removed on job pages so the job's own win.
_DESCRIPTION = re.compile(r'<meta\s+(?:name="description"|property="og:[a-z_]+")[^>]*>\s*', re.S)

FALLBACK_INDEX = """<!doctype html><html lang="en"><head><meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>FirstOffer</title></head>
<body><p>The dashboard is not built yet: run <code>cd dashboard && npm run build</code>.</p></body></html>"""


def public_base_url(request_base: str) -> str:
    """The site's public address: DASHBOARD_URL when set (it is behind a proxy on Render), else the request's."""
    return (settings.dashboard_url or request_base).rstrip("/")


def job_place(job: Job) -> str:
    if job.city and job.country:
        return f"{job.city}, {job.country}"
    return job.city or job.country or job.location or ""


def plain_text(value: str | None, limit: int) -> str:
    text = _SPACES.sub(" ", html.unescape(_TAGS.sub(" ", value or ""))).strip()
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)  # "<b>fresher</b>." became "fresher ."
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def share_summary(job: Job) -> str:
    """One line for link previews: where, what level, then the start of the description."""
    parts = [job.company]
    if place := job_place(job):
        parts.append(place)
    if job.is_remote:
        parts.append("Remote")
    if job.experience_level in ("intern", "fresher", "junior"):
        parts.append({"intern": "Internship", "fresher": "Fresher-friendly", "junior": "Junior"}[job.experience_level])
    summary = " · ".join(parts)
    if job.description:
        summary += " — " + plain_text(job.description, 160)
    return summary


def job_posting_ld(job: Job, url: str) -> dict:
    """schema.org JobPosting, which lets search engines list the job (https://schema.org/JobPosting)."""
    posted = as_utc(job.posted_at or job.first_seen_at)
    data = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job.title,
        "description": job.description or f"{job.title} at {job.company}. Apply on {job.company}'s careers site.",
        "datePosted": posted.date().isoformat() if posted else None,
        "hiringOrganization": {"@type": "Organization", "name": job.company},
        "url": url,
        "directApply": False,
    }
    if job.employment_type:
        data["employmentType"] = job.employment_type
    if job.is_remote:
        data["jobLocationType"] = "TELECOMMUTE"
    if job.city or job.country:
        address = {"@type": "PostalAddress"}
        if job.city:
            address["addressLocality"] = job.city
        if job.country:
            address["addressCountry"] = job.country
        data["jobLocation"] = {"@type": "Place", "address": address}
    elif job.is_remote and job.country:
        data["applicantLocationRequirements"] = {"@type": "Country", "name": job.country}
    return {k: v for k, v in data.items() if v is not None}


def _index_html() -> str:
    index = DASHBOARD_DIR / "index.html"
    return index.read_text(encoding="utf-8") if index.is_file() else FALLBACK_INDEX


def render_job_page(job: Job | None, base_url: str) -> str:
    """The dashboard page with tags describing one job (or a "not found" title when job is None)."""
    page = _index_html()
    brand = settings.brand_name
    if job is None:
        title = f"Job not found · {brand}"
        tags = ['<meta name="robots" content="noindex" />']
    else:
        url = f"{base_url}/job/{job.id}"
        title = f"{job.title} at {job.company} · {brand}"
        summary = share_summary(job)
        if not job.active:
            summary = "This opening has closed. " + summary
        e = lambda s: html.escape(s, quote=True)  # noqa: E731
        tags = [
            f'<meta name="description" content="{e(summary)}" />',
            f'<link rel="canonical" href="{e(url)}" />',
            '<meta property="og:type" content="website" />',
            f'<meta property="og:site_name" content="{e(brand)}" />',
            f'<meta property="og:title" content="{e(job.title + " at " + job.company)}" />',
            f'<meta property="og:description" content="{e(summary)}" />',
            f'<meta property="og:url" content="{e(url)}" />',
            '<meta name="twitter:card" content="summary" />',
            f'<meta name="twitter:title" content="{e(job.title + " at " + job.company)}" />',
            f'<meta name="twitter:description" content="{e(summary)}" />',
        ]
        if job.active:
            # "</" inside JSON could close the script tag early; < keeps the JSON valid and the HTML safe.
            ld = json.dumps(job_posting_ld(job, url), ensure_ascii=False).replace("<", "\\u003c")
            tags.append(f'<script type="application/ld+json">{ld}</script>')
        else:
            tags.append('<meta name="robots" content="noindex" />')
    page = _DESCRIPTION.sub("", page) if job is not None else page
    page = _TITLE.sub(lambda _: f"<title>{html.escape(title)}</title>", page, count=1)
    return page.replace("</head>", "    " + "\n    ".join(tags) + "\n  </head>", 1)


def robots_txt(base_url: str) -> str:
    return f"User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: {base_url}/sitemap.xml\n"


def sitemap_xml(base_url: str, jobs: list[tuple[int, object]]) -> str:
    """Home page plus each open job's share page, newest first (at most 50,000 URLs per the sitemap spec)."""
    urls = [f"<url><loc>{xml_escape(base_url)}/</loc><changefreq>hourly</changefreq></url>"]
    for job_id, seen in jobs[:49_999]:
        lastmod = f"<lastmod>{as_utc(seen).date().isoformat()}</lastmod>" if seen else ""
        urls.append(f"<url><loc>{xml_escape(base_url)}/job/{job_id}</loc>{lastmod}</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")
