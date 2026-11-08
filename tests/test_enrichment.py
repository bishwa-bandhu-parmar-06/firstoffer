from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.classify import classify_category, classify_experience
from app.db import SessionLocal, init_db
from app.enrich import dedup_key, enrich_job, refresh_groups
from app.locations import parse_location
from app.models import Job


@pytest.mark.parametrize("raw, city, country", [
    ("Noida, UP, IN, 201301", "Noida", "India"),
    ("Bangalore, IN", "Bengaluru", "India"),
    ("Hyderabad, Telangana, IND", "Hyderabad", "India"),
    ("Sunnyvale, CA", "Sunnyvale", "United States"),
    ("Toronto, ON, CA, M5H 0B3 +1 more…", "Toronto", "Canada"),
    ("US-CA-Menlo Park", "Menlo Park", "United States"),
    ("CA-Ontario-Toronto", "Toronto", "Canada"),
    ("United States, Washington, Redmond", "Redmond", "United States"),
    ("Israel, Tel Aviv", "Tel Aviv", "Israel"),
    ("JPN - TOKYO", "Tokyo", "Japan"),
    ("Bellevue, Washington", "Bellevue", "United States"),
    ("Washington, DC", "Washington", "United States"),
    ("Issy-les-Moulineaux, FR", "Issy-les-Moulineaux", "France"),
    ("Chennai, Tamil Nādu, India", "Chennai", "India"),
    ("Cairo - ETIC", "Cairo", "Egypt"),
    ("Mexico - Mexico City", "Mexico City", "Mexico"),
    ("Taipei, TW", "Taipei", "Taiwan"),
    ("USA.VA.Reston", "Reston", "United States"),
    ("Bengaluru Millenia", "Bengaluru", "India"),
    ("Gurugram 10 C", "Gurugram", "India"),
    ("Warszawa", "Warsaw", "Poland"),
    ("Makati", "Makati", "Philippines"),
    ("Hybrid", None, None),
    ("3 Locations", None, None),
])
def test_parse_location(raw, city, country):
    parsed = parse_location(raw)
    assert (parsed.city, parsed.country) == (city, country)


def test_parse_location_multiple_and_remote():
    parsed = parse_location("Bengaluru - India; Remote - India; Remote - United States")
    assert parsed.city == "Bengaluru"
    assert parsed.countries == ["India", "United States"]
    assert parsed.is_remote
    assert parse_location("Pune, India", "Remote").is_remote
    assert not parse_location("Pune, India", "Hybrid").is_remote


@pytest.mark.parametrize("title, description, level", [
    ("Software Engineering Intern", None, "intern"),
    ("Summer Internship 2027 - Data", None, "intern"),
    ("Graduate Engineer Trainee", None, "fresher"),
    ("New Grad Software Engineer", None, "fresher"),
    ("Software Engineer I", None, "fresher"),
    ("Associate Software Engineer", None, "junior"),
    ("Software Engineer II", None, "junior"),
    ("Senior Software Engineer", None, "senior"),
    ("SDE III", None, "senior"),
    ("Director, Cloud Engineering", None, "leadership"),
    ("Graduate Staff | GFS Assurance", None, "fresher"),
    ("Campus Recruiting Manager", None, "senior"),
    ("Java Developer", "<li>0-2 years of experience in Java</li>", "fresher"),
    ("Java Developer", "Freshers from the 2026 batch are welcome", "fresher"),
    ("Data Analyst", "<p>3+ years of relevant work experience</p>", "mid"),
    ("Backend Engineer", "Minimum of 8 years in distributed systems", "senior"),
    ("Backend Engineer", "Great team, great snacks", None),
])
def test_classify_experience(title, description, level):
    assert classify_experience(title, description)[0] == level


@pytest.mark.parametrize("title, department, category", [
    ("Senior Software Engineer", None, "software"),
    ("Data Scientist", None, "data_ai"),
    ("Machine Learning Engineer", None, "data_ai"),
    ("Site Reliability Engineer", None, "devops_cloud"),
    ("Cloud Infrastructure Engineer", None, "devops_cloud"),
    ("SOC Analyst", None, "security"),
    ("QA Automation Engineer", None, "qa_testing"),
    ("ASIC Design Verification Engineer", None, "hardware_embedded"),
    ("Network Engineer", None, "networking"),
    ("Service Desk Analyst", None, "it_support"),
    ("SAP FICO Consultant", None, "consulting_tech"),
    ("Product Manager", None, "product_design"),
    ("Account Executive, Mid Market", None, "non_it"),
    ("Software Sales Representative", None, "non_it"),
    ("Warehouse Associate", None, "non_it"),
    ("Security Guard", None, "non_it"),
    ("Mechanical Engineer", None, "non_it"),
    ("Associate", "Engineering", "software"),
    ("Associate", None, "other"),
    ("Hyderabad TECHNO FUNCTIONAL CONSULTANT L2 IND 500032", None, "consulting_tech"),
    ("Bengaluru LEAD ADMINISTRATOR L1 IND 560035", None, "it_support"),
])
def test_classify_category(title, department, category):
    assert classify_category(title, department) == category


def test_dedup_key_ignores_case_punctuation_and_req_ids():
    assert dedup_key("Acme", "Software Engineer (Req #1234)", "Pune") == dedup_key("ACME", "software engineer", "pune")
    assert dedup_key("Acme", "Software Engineer", "Pune") != dedup_key("Acme", "Software Engineer", "Chennai")


def _job(**values):
    now = datetime.now(timezone.utc)
    defaults = dict(source_provider="fake", source_key="fake:x", company="Acme", apply_url="https://x",
                    first_seen_at=now, last_seen_at=now, active=True)
    job = Job(**{**defaults, **values})
    enrich_job(job)
    return job


def test_jobs_api_filters_search_and_collapse(fresh_db):
    init_db()  # build the full-text index for the fresh database
    old = datetime.now(timezone.utc) - timedelta(days=40)
    with SessionLocal() as db:
        db.add_all([
            _job(source_job_id="1", title="Graduate Software Engineer", location="Pune, India"),
            _job(source_job_id="2", title="Graduate Software Engineer", location="Pune, India"),  # re-post of 1
            _job(source_job_id="3", title="Senior Data Scientist", location="Seattle, WA, United States", workplace_type="Remote"),
            _job(source_job_id="4", title="Account Executive", location="London, UK", posted_at=old),
        ])
        db.commit()
        for job in db.scalars(select(Job)):
            enrich_job(job)  # listed_at needs first_seen_at, which the database fills in
        db.commit()
        refresh_groups(db)
    from app import main
    main._filters_cache.clear()

    from app.main import app
    client = TestClient(app)

    body = client.get("/jobs").json()
    assert body["total"] == 3
    grad = next(i for i in body["items"] if i["title"] == "Graduate Software Engineer")
    assert grad["similar_count"] == 2 and grad["experience_level"] == "fresher" and grad["country"] == "India"
    assert client.get("/jobs", params={"collapse": "false"}).json()["total"] == 4

    def titles(**params):
        return sorted(i["title"] for i in client.get("/jobs", params=params).json()["items"])

    assert titles(experience="fresher,intern") == ["Graduate Software Engineer"]
    assert titles(it_only="true") == ["Graduate Software Engineer", "Senior Data Scientist"]
    assert titles(country="United States") == ["Senior Data Scientist"]
    assert titles(remote="true") == ["Senior Data Scientist"]
    assert titles(q="softw") == ["Graduate Software Engineer"]
    assert titles(q="data seattle") == ["Senior Data Scientist"]
    assert titles(posted_within_days=30) == ["Graduate Software Engineer", "Senior Data Scientist"]
    assert titles(category="non_it") == ["Account Executive"]

    detail = client.get(f"/jobs/{grad['id']}").json()
    assert len(detail["similar_postings"]) == 1
    options = client.get("/filters").json()
    assert {e["value"]: e["count"] for e in options["experience"]}["fresher"] == 2
    assert options["countries"][0] == {"value": "India", "count": 2}
