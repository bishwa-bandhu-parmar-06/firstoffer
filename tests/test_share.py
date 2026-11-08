import json
import re
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app import share
from app.db import SessionLocal
from app.main import app
from app.models import Job

INDEX = """<!doctype html><html><head>
<meta name="description" content="Generic description" />
<meta property="og:title" content="Generic title" />
<title>FirstOffer · IT jobs for freshers</title>
</head><body><div id="root"></div></body></html>"""


@pytest.fixture
def client(fresh_db, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    monkeypatch.setattr(share, "DASHBOARD_DIR", tmp_path)
    monkeypatch.setattr(share.settings, "dashboard_url", "https://firstoffer.example")
    return TestClient(app)


def add_job(**overrides) -> int:
    fields = dict(
        source_provider="greenhouse", source_key="gh:acme", source_job_id="1", company="Acme <Labs>",
        title='Graduate "Software" Engineer </script>', apply_url="https://acme.example/jobs/1",
        city="Pune", country="India", experience_level="fresher", is_primary=True, active=True,
        description="<p>Join us as a <b>fresher</b>. 0-1 years.</p>",
        first_seen_at=datetime(2026, 11, 1, tzinfo=timezone.utc), last_seen_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
        listed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    with SessionLocal() as db:
        job = Job(**fields)
        db.add(job)
        db.commit()
        return job.id


def test_shared_job_page_has_job_preview_tags(client):
    job_id = add_job()
    response = client.get(f"/job/{job_id}")
    assert response.status_code == 200
    page = response.text
    # Job-specific tags replace the generic ones, and everything from the posting is escaped.
    assert "Generic" not in page
    assert '<title>Graduate &quot;Software&quot; Engineer &lt;/script&gt; at Acme &lt;Labs&gt; · FirstOffer</title>' in page
    assert f'<meta property="og:url" content="https://firstoffer.example/job/{job_id}" />' in page
    assert f'<link rel="canonical" href="https://firstoffer.example/job/{job_id}" />' in page
    assert "Pune, India · Fresher-friendly — Join us as a fresher. 0-1 years." in page
    # The only </script> in the page is the JSON-LD block's own closing tag.
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1)
    data = json.loads(ld)
    assert data["@type"] == "JobPosting"
    assert data["hiringOrganization"]["name"] == "Acme <Labs>"
    assert data["jobLocation"]["address"] == {"@type": "PostalAddress", "addressLocality": "Pune", "addressCountry": "India"}
    assert data["datePosted"] == "2026-11-01"


def test_closed_job_page_says_so_and_is_not_indexed(client):
    job_id = add_job(active=False)
    page = client.get(f"/job/{job_id}").text
    assert "This opening has closed." in page
    assert 'name="robots" content="noindex"' in page
    assert "application/ld+json" not in page


def test_missing_job_page_is_404_but_still_loads_the_app(client):
    response = client.get("/job/999999")
    assert response.status_code == 404
    assert '<div id="root"></div>' in response.text
    assert "Job not found" in response.text


def test_sitemap_lists_open_primary_jobs_only(client):
    share_id = add_job()
    closed_id = add_job(source_job_id="2", active=False)
    repost_id = add_job(source_job_id="3", is_primary=False)
    import app.main as main
    main._sitemap_cache = None
    xml = client.get("/sitemap.xml").text
    assert f"https://firstoffer.example/job/{share_id}</loc><lastmod>2026-11-07</lastmod>" in xml
    assert f"/job/{closed_id}<" not in xml
    assert f"/job/{repost_id}<" not in xml


def test_robots_points_to_sitemap(client):
    text = client.get("/robots.txt").text
    assert "Sitemap: https://firstoffer.example/sitemap.xml" in text
    assert "Disallow: /admin/" in text


def test_site_info(client, monkeypatch):
    monkeypatch.setattr(share.settings, "telegram_channel_url", "https://t.me/firstoffer_jobs")
    assert client.get("/site").json() == {"brand_name": "FirstOffer", "telegram_channel_url": "https://t.me/firstoffer_jobs"}
