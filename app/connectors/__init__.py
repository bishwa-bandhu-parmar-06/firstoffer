"""One connector per hiring platform (or per company, for companies with their own careers API). Each module exposes:

- KEY_FIELDS: the source settings that identify one job board (also validated as required).
- async fetch_jobs(http, source) -> FetchResult
- optional async fetch_details(http, source, source_job_id, apply_url) -> dict of extra job fields,
  for platforms whose job list leaves out the full description.
- optional DETAIL_FIELDS: fields the detail call knows better than the list; once details are
  fetched, later listings don't overwrite them.
"""
from app.connectors import (
    amazon, ashby, atlassian, capgemini, eightfold, greenhouse, jibe, lever, njoyn, oracle, phenom,
    sitemap, smartrecruiters, successfactors, tencent, workday,
)

CONNECTORS = {
    # Hiring platforms
    "ashby": ashby,
    "eightfold": eightfold,
    "greenhouse": greenhouse,
    "jibe": jibe,
    "lever": lever,
    "njoyn": njoyn,
    "oracle": oracle,
    "phenom": phenom,
    "smartrecruiters": smartrecruiters,
    "successfactors": successfactors,
    "workday": workday,
    # Any site with a crawlable sitemap of job pages
    "sitemap": sitemap,
    # Company-specific careers APIs
    "amazon": amazon,
    "atlassian": atlassian,
    "capgemini": capgemini,
    "tencent": tencent,
}
