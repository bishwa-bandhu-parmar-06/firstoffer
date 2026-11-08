"""Tencent careers JSON (careers.tencent.com). Settings: "host", optional "language" (default "en-us")."""
from app.config import settings
from app.connectors.base import FetchResult, make_job, valid_jobs, join_nonempty
from app.connectors.pages import parse_date

KEY_FIELDS = ("host",)
PAGE_SIZE = 100


async def fetch_jobs(http, source: dict) -> FetchResult:
    language = source.get("language", "en-us")
    jobs, page, total = [], 1, None
    while total is None or len(jobs) < total:
        data = await http.get_json(f"https://{source['host']}/tencentcareer/api/post/Query", params={
            "pageIndex": page, "pageSize": PAGE_SIZE, "language": language, "area": language,
        })
        body = data.get("Data") or {}
        total = body.get("Count") or 0
        posts = body.get("Posts") or []
        if not posts:
            break
        for p in posts:
            experience = p.get("RequireWorkYearsName")
            responsibility = (p.get("Responsibility") or "").replace("\r\n", "\n")
            description = (f"<p><strong>Experience:</strong> {experience}</p>" if experience else "") + \
                          (f"<div style=\"white-space: pre-line\">{responsibility}</div>" if responsibility else "")
            jobs.append(make_job(
                source_job_id=p.get("PostId"),
                title=p.get("RecruitPostName"),
                location=join_nonempty([p.get("LocationName"), p.get("CountryName")], ", "),
                description=description or None,
                apply_url=(p.get("PostURL") or "").replace("http://", "https://", 1) or None,
                department=join_nonempty([p.get("BGName"), p.get("CategoryName")], " / "),
                posted_at=parse_date(p.get("LastUpdateTime")),
            ))
        page += 1
        if len(jobs) >= settings.max_jobs_per_source:
            return FetchResult(valid_jobs(jobs[:settings.max_jobs_per_source]), complete=False)
    return FetchResult(valid_jobs(jobs))
