import asyncio
import json
from datetime import datetime, timezone
import httpx
from app.connectors import ashby, eightfold, greenhouse, lever, oracle, smartrecruiters, workday
from tests.conftest import make_http


def run(coro):
    return asyncio.run(coro)


def test_greenhouse_unescapes_html_and_maps_fields():
    def handler(request):
        assert request.url.path == "/v1/boards/acme/jobs"
        assert request.url.params["content"] == "true"
        return httpx.Response(200, json={"jobs": [{
            "id": 123, "title": "Software Engineer", "location": {"name": "Bengaluru"},
            "content": "&lt;p&gt;Build things&lt;/p&gt;", "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "departments": [{"name": "Engineering"}, {"name": "Platform"}],
            "first_published": "2026-10-01T09:00:00-04:00",
        }]})

    result = run(greenhouse.fetch_jobs(make_http(handler), {"board_token": "acme"}))
    job = result.jobs[0]
    assert result.complete
    assert job["source_job_id"] == "123"
    assert job["description"] == "<p>Build things</p>"
    assert job["department"] == "Engineering, Platform"
    assert job["posted_at"] == datetime(2026, 10, 1, 13, tzinfo=timezone.utc)


def test_lever_parses_millisecond_created_at():
    def handler(request):
        return httpx.Response(200, json=[{
            "id": "abc", "text": "Data Analyst", "createdAt": 1792767640768,
            "categories": {"location": "Remote", "commitment": "Full-time", "team": "Data"},
            "description": "<p>Intro</p>", "lists": [{"text": "Requirements", "content": "<li>SQL</li>"}],
            "hostedUrl": "https://jobs.lever.co/acme/abc",
        }])

    job = run(lever.fetch_jobs(make_http(handler), {"site": "acme"})).jobs[0]
    assert job["posted_at"] == datetime.fromtimestamp(1792767640.768, tz=timezone.utc)
    assert "<li>SQL</li>" in job["description"]
    assert job["employment_type"] == "Full-time"


def test_ashby_skips_unlisted_jobs():
    def handler(request):
        return httpx.Response(200, json={"jobs": [
            {"id": "1", "title": "Listed", "isListed": True, "location": "India",
             "secondaryLocations": [{"location": "Remote"}], "jobUrl": "https://jobs.ashbyhq.com/acme/1"},
            {"id": "2", "title": "Hidden", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/acme/2"},
        ]})

    jobs = run(ashby.fetch_jobs(make_http(handler), {"org": "acme"})).jobs
    assert [j["title"] for j in jobs] == ["Listed"]
    assert jobs[0]["location"] == "India; Remote"


def test_smartrecruiters_paginates_and_fetches_details():
    def handler(request):
        if request.url.path.endswith("/postings"):
            offset = int(request.url.params["offset"])
            content = [{"id": str(i), "name": f"Job {i}", "location": {"fullLocation": "Pune, India", "remote": i == 0}}
                       for i in range(offset, min(offset + 100, 101))]
            return httpx.Response(200, json={"totalFound": 101, "content": content})
        return httpx.Response(200, json={
            "postingUrl": "https://jobs.smartrecruiters.com/Acme/7-job",
            "jobAd": {"sections": {"jobDescription": {"title": "Job Description", "text": "<p>Do work</p>"}}},
        })

    http = make_http(handler)
    result = run(smartrecruiters.fetch_jobs(http, {"company_id": "Acme"}))
    assert len(result.jobs) == 101 and result.complete
    assert result.jobs[0]["workplace_type"] == "Remote"
    details = run(smartrecruiters.fetch_details(http, {"company_id": "Acme"}, "7"))
    assert "<p>Do work</p>" in details["description"]
    assert details["apply_url"].endswith("7-job")


def test_workday_posted_on_parsing():
    now = datetime(2026, 10, 28, 15, tzinfo=timezone.utc)
    assert workday.parse_posted_on("Posted Today", now) == datetime(2026, 10, 28, tzinfo=timezone.utc)
    assert workday.parse_posted_on("Posted Yesterday", now) == datetime(2026, 10, 27, tzinfo=timezone.utc)
    assert workday.parse_posted_on("Posted 3 Days Ago", now) == datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert workday.parse_posted_on("Posted 30+ Days Ago", now) is None


def test_workday_splits_capped_search_by_facet():
    facets = [
        {"facetParameter": "timeType", "values": [{"id": "ft", "count": 2600}, {"id": "pt", "count": 1}]},
        {"facetParameter": "locationMainGroup", "values": [
            {"facetParameter": "locationHierarchy1", "values": [{"id": f"c{i}", "count": 100} for i in range(30)]},
        ]},
        {"facetParameter": "jobFamilyGroup", "values": [{"id": "eng", "count": 1500}, {"id": "sales", "count": 1100}]},
    ]
    applied_seen = []

    def handler(request):
        body = json.loads(request.content)
        applied = body["appliedFacets"]
        applied_seen.append(applied)
        if not applied:
            return httpx.Response(200, json={"total": 2000, "jobPostings": [], "facets": facets})
        group = applied["jobFamilyGroup"][0]
        if body["offset"] > 0:
            return httpx.Response(200, json={"total": 0, "jobPostings": []})
        postings = [{"title": f"{group} {i}", "externalPath": f"/job/x/{group}_{i}", "locationsText": "India",
                     "postedOn": "Posted Today"} for i in range(3)]
        return httpx.Response(200, json={"total": 3, "jobPostings": postings})

    source = {"host": "acme.wd5.myworkdayjobs.com", "tenant": "acme", "site": "External"}
    result = run(workday.fetch_jobs(make_http(handler), source))
    # jobFamilyGroup covers everything in 2 searches; the 30-country facet would need 30.
    assert {tuple(a) for a in applied_seen if a} == {("jobFamilyGroup",)}
    assert len(result.jobs) == 6 and result.complete
    assert result.jobs[0]["apply_url"] == "https://acme.wd5.myworkdayjobs.com/External/job/x/eng_0"


def test_eightfold_pcsx_paginates():
    def handler(request):
        start = int(request.url.params["start"])
        positions = [{"id": i, "name": f"Job {i}", "locations": ["Hyderabad, India"], "postedTs": 1793186101,
                      "positionUrl": f"/careers/job/{i}"} for i in range(start, min(start + 10, 12))]
        return httpx.Response(200, json={"status": 200, "data": {"count": 12, "positions": positions}})

    source = {"host": "jobs.acme.com", "domain": "acme.com", "api": "pcsx"}
    result = run(eightfold.fetch_jobs(make_http(handler), source))
    assert len(result.jobs) == 12
    assert result.jobs[0]["apply_url"] == "https://jobs.acme.com/careers/job/0"


def test_oracle_maps_requisitions():
    def handler(request):
        assert "siteNumber=CX_1" in request.url.params["finder"]
        return httpx.Response(200, json={"items": [{"TotalJobsCount": 1, "requisitionList": [{
            "Id": "42", "Title": "Graduate Engineer", "PrimaryLocation": "Chennai, India",
            "secondaryLocations": [{"Name": "Pune, India"}], "PostedDate": "2026-10-20",
            "ShortDescriptionStr": "Join us", "WorkplaceType": "On-site",
        }]}]})

    source = {"host": "x.fa.ocs.oraclecloud.com", "site": "CX_1"}
    job = run(oracle.fetch_jobs(make_http(handler), source)).jobs[0]
    assert job["location"] == "Chennai, India; Pune, India"
    assert job["apply_url"] == "https://x.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/42"
    assert job["posted_at"] == datetime(2026, 10, 20, tzinfo=timezone.utc)


def test_http_retries_on_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    from app.http import Http
    http = Http(httpx.AsyncClient(transport=httpx.MockTransport(handler)), min_interval=0, retries=2)
    assert run(http.get_json("https://example.com/x")) == {"ok": True}
    assert len(calls) == 2
