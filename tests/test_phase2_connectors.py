import asyncio
from datetime import datetime, timezone
import httpx
from app.connectors import amazon, atlassian, capgemini, jibe, njoyn, phenom, sitemap, successfactors, tencent
from app.connectors.pages import parse_job_page, title_from_slug, job_id_from_url
from tests.conftest import make_http


def run(coro):
    return asyncio.run(coro)


def test_title_and_id_from_job_urls():
    assert title_from_slug("https://x.com/job/Senior-Data-Engineer/1234/") == "Senior Data Engineer"
    assert title_from_slug("https://x.com/job/BusinessAnalyst/79204") == "Business Analyst"
    assert title_from_slug("https://x.com/job/Pune-L1%28CONTRACT%29/9/") == "Pune L1(CONTRACT)"
    assert job_id_from_url("https://x.com/job/Senior-Data-Engineer/1234/") == "1234"


def test_parse_job_page_prefers_json_ld():
    page = """<html><head><title>Ignore me</title><script type="application/ld+json">
    {"@context": "http://schema.org", "@type": "JobPosting", "title": "Graduate Analyst", "datePosted": "2026-10-01",
     "description": "<p>Learn</p>", "jobLocation": {"address": {"addressLocality": "Pune", "addressCountry": "IN"}}}
    </script></head></html>"""
    result = parse_job_page(page)
    assert result["title"] == "Graduate Analyst"
    assert result["location"] == "Pune, IN"
    assert result["posted_at"] == datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_parse_job_page_itemprop_and_title_cleanup():
    page = """<html><head><title>Data Analyst Job Details | EY</title></head><body>
    <span itemprop="description"><p>Analyse data</p></span><meta itemprop="datePosted" content="Oct 2, 2026"></body></html>"""
    result = parse_job_page(page)
    assert result["title"] == "Data Analyst"
    assert result["description"] == "<p>Analyse data</p>"
    assert result["posted_at"] == datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert parse_job_page("<title>\n  Tax Manager -  - 360763\n</title>")["title"] == "Tax Manager"


def test_sitemap_follows_index_and_filters_job_urls():
    def handler(request):
        if request.url.path == "/index.xml":
            return httpx.Response(200, text="<sitemapindex><sitemap><loc>https://x.com/a.xml</loc></sitemap></sitemapindex>")
        return httpx.Response(200, text="""<urlset>
          <url><loc>https://x.com/job/Junior-Developer/11/</loc><lastmod>2026-10-24</lastmod></url>
          <url><loc>https://x.com/about</loc></url></urlset>""")

    result = run(sitemap.fetch_jobs(make_http(handler), {"sitemap": "https://x.com/index.xml"}))
    assert [(j["source_job_id"], j["title"]) for j in result.jobs] == [("11", "Junior Developer")]
    assert result.jobs[0]["posted_at"] is None  # lastmod is not a posting date


def test_successfactors_search_pages():
    def page(start):
        rows = "".join(
            f'<tr class="data-row"><td><a class="jobTitle-link" href="/job/Role-{i}/{i}/">Role {i}</a></td>'
            f'<td><span class="jobLocation">Pune, IN</span></td><td><span class="jobDate">Oct 28, 2026</span></td></tr>'
            for i in range(start, min(start + 25, 30)))
        return f'<span class="paginationLabel">Results {start + 1} – {min(start + 25, 30)} of 30</span><table>{rows}</table>'

    def handler(request):
        return httpx.Response(200, text=page(int(request.url.params["startrow"])))

    result = run(successfactors.fetch_jobs(make_http(handler), {"host": "careers.x.com"}))
    assert len(result.jobs) == 30
    job = result.jobs[0]
    assert job["apply_url"] == "https://careers.x.com/job/Role-0/0/" and job["location"] == "Pune, IN"
    assert job["posted_at"] == datetime(2026, 10, 28, tzinfo=timezone.utc)


def test_njoyn_pages_through_listing_form():
    def listing(page):
        row = (f'<tr><td>J{page}</td><td><a href="xweb.asp?NTKN=c&clid=1&Page=JobDetails&Jobid=J{page}">Dev {page}</a></td>'
               f'<td>Software</td><td>ALL</td><td>Canada</td></tr>')
        return f"<table>{row}</table><div>Page {page} of 2</div>"

    def handler(request):
        return httpx.Response(200, text=listing(2 if request.method == "POST" else 1))

    result = run(njoyn.fetch_jobs(make_http(handler), {"host": "cgi.njoyn.com", "clid": "1"}))
    assert [j["source_job_id"] for j in result.jobs] == ["J1", "J2"] and result.complete
    assert result.jobs[0]["location"] == "Canada"
    assert result.jobs[0]["apply_url"].startswith("https://cgi.njoyn.com/CORP/xweb/xweb.asp?")


def test_amazon_splits_countries_over_the_cap():
    requested = []

    def handler(request):
        params = request.url.params
        requested.append(dict(params))
        if params.get("facets[]") == "normalized_country_code":
            return httpx.Response(200, json={"facets": {"normalized_country_code_facet": [{"USA": 12000}, {"IND": 1}]}})
        if params.get("facets[]") == "business_category":
            return httpx.Response(200, json={"facets": {"business_category_facet": [{"aws": 1}]}})
        country = params["normalized_country_code[]"]
        return httpx.Response(200, json={"jobs": [{"id_icims": country, "title": "SDE", "job_path": f"/en/jobs/{country}",
                                                   "posted_date": "May 13, 2026", "description": "Build"}]})

    result = run(amazon.fetch_jobs(make_http(handler), {"host": "www.amazon.jobs"}))
    assert sorted(j["source_job_id"] for j in result.jobs) == ["IND", "USA"]
    assert any(p.get("business_category[]") == "aws" for p in requested)
    assert result.jobs[0]["posted_at"] == datetime(2026, 5, 13, tzinfo=timezone.utc)


def test_jibe_capgemini_tencent_atlassian_phenom_mapping():
    def handler(request):
        host, path = request.url.host, request.url.path
        if host == "careers.amd.com":
            return httpx.Response(200, json={"totalCount": 1, "jobs": [{"data": {
                "slug": "9", "req_id": "9", "title": "Intern", "full_location": "Hyderabad, India",
                "employment_type": "FULL_TIME", "description": "<p>a</p>", "posted_date": "2026-10-28T10:15:00+0000"}}]})
        if host == "www.capgemini.com" and path.endswith("/jobs"):
            return httpx.Response(200, json={"total_pages": 1, "items": [{"id": "c1", "title": "Analyst", "location": "Pune",
                                             "country_code": "en-in", "html_url": "https://www.capgemini.com/jobs/c1/"}]})
        if host == "www.capgemini.com":
            return httpx.Response(200, json={"content": "Do things", "experience_level": "Freshers"})
        if host == "careers.tencent.com":
            return httpx.Response(200, json={"Data": {"Count": 1, "Posts": [{"PostId": "t1", "RecruitPostName": "Engineer",
                                  "LocationName": "Shenzhen", "CountryName": "China", "LastUpdateTime": "October 28,2026",
                                  "PostURL": "http://careers.tencent.com/jobdesc.html?postId=t1"}]}})
        if host == "www.atlassian.com":
            return httpx.Response(200, json=[{"id": 1, "title": "Grad SWE", "locations": ["Bengaluru - India -   Bengaluru,  560071 India"],
                                              "portalJobPost": {"portalUrl": "https://x.icims.com/jobs/1", "updatedDate": "2026-10-23 06:28 AM"}}])
        return httpx.Response(200, json={"refineSearch": {"totalHits": 1, "data": {"jobs": [
            {"jobId": "393547", "title": "PLM Support Engineer", "location": "Chennai, India", "applyUrl": "https://staging/x"}]}}})

    http = make_http(handler)
    amd = run(jibe.fetch_jobs(http, {"host": "careers.amd.com"})).jobs[0]
    assert amd["apply_url"] == "https://careers.amd.com/careers-home/jobs/9" and amd["employment_type"] == "Full Time"
    cap = run(capgemini.fetch_jobs(http, {"host": "www.capgemini.com"})).jobs[0]
    assert cap["location"] == "Pune, IN"
    assert "Freshers" in run(capgemini.fetch_details(http, {"host": "www.capgemini.com"}, "c1"))["description"]
    ten = run(tencent.fetch_jobs(http, {"host": "careers.tencent.com"})).jobs[0]
    assert ten["apply_url"].startswith("https://") and ten["posted_at"] == datetime(2026, 10, 28, tzinfo=timezone.utc)
    atl = run(atlassian.fetch_jobs(http, {"host": "www.atlassian.com"})).jobs[0]
    assert atl["location"] == "Bengaluru - India"
    ntt = run(phenom.fetch_jobs(http, {"host": "careers.nttdata.com", "lang": "en_global", "job_url_prefix": "/global/en"})).jobs[0]
    assert ntt["apply_url"] == "https://careers.nttdata.com/global/en/job/393547/PLM-Support-Engineer"
