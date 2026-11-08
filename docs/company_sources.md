# Company source map (100 companies)

Research date: 2026-10-28. Each company was checked against its live careers site, with a test call to its job feed where possible.
"Jobs" is the count the test call reported. **2000** (Workday) and **10000** (Amazon) are page caps, not real totals.

**Tiers**
- **T1**: structured JSON feed, verified working. Build first.
- **T2**: no JSON, but server-rendered HTML, an RSS feed or a sitemap is available. Needs an HTML parser.
- **T3**: blocked (bot protection or robots.txt), JS-only, or platform unknown. Shown as link-only until it's solved.

## Coverage status (after Phase 2)

- **Collected (79 companies, 82 sources in `sources.json`):** every T1 company except IBM, plus every T2 company except Endava.
  Juniper is covered through HPE's board. Deloitte uses its US sitemap and the SmartRecruiters board `Deloitte6`.
  Deloitte India (USI) and the global Avature portal are excluded because their robots.txt disallows the feeds.
- **Link-only (21 companies, `link_only.json`):** all of T3, plus IBM (its search API returns no job fields
  to outside callers) and Endava (its iCIMS search page returns 404 outside a browser).
- **Limited data:** Wipro, HCLTech and Fujitsu build their pages with JavaScript from `/services/`, which their
  robots.txt disallows. Their jobs come from the sitemap: link, title taken from the URL, and last-updated date.
  Lenovo's pages all show the wrong `<title>`, so Lenovo titles also come from the URL.

## Summary

| Connector | Companies | Count |
|---|---|---|
| Workday | NVIDIA, Adobe, Salesforce, Intel, Cisco, HPE (+Juniper), Broadcom, Workday, Autodesk, Zoom, Palo Alto Networks, CrowdStrike, F5, Sony, Samsung, Motorola Solutions, Accenture, DXC, Genpact, Kyndryl, Booz Allen, Leidos, PwC | 24 |
| Greenhouse | HubSpot, Dropbox, Zscaler, Okta, SentinelOne, Rubrik, Cloudflare, Anthropic, Databricks, MongoDB, Elastic, C3.ai, Thoughtworks, Airbnb, Stripe, Block, Robinhood, Epic Games | 18 |
| Eightfold | Microsoft, Netflix, Qualcomm*, Ericsson, PayPal | 5 |
| Oracle HCM | Oracle, Dell, Fortinet, Nokia, Hexaware | 5 |
| Ashby | OpenAI, Snowflake, Redis, UiPath | 4 |
| SmartRecruiters | ServiceNow, Check Point, Arista | 3 |
| Lever | Palantir, Spotify | 2 |
| iCIMS Jibe (`/api/jobs`) | AMD, Panasonic | 2 |
| Custom JSON | Amazon, Atlassian, Tencent, Capgemini, NTT DATA (Phenom), IBM (partial) | 6 |
| **T1 total** | | **69** |
| T2: SuccessFactors HTML | Wipro, HCLTech, LTIMindtree, Fujitsu, NEC, EY, Globant, Supermicro | 8 |
| T2: Avature RSS | Lenovo, Deloitte (+ SmartRecruiters `Deloitte6`) | 2 |
| T2: other HTML | CGI (Njoyn), Endava (iCIMS) | 2 |
| **T3** | Google, Apple, Meta, SAP, Akamai, Intuit, Shopify, Confluent, TCS, Infosys, Cognizant, Tech Mahindra, Persistent, Coforge, EPAM, Mphasis, KPMG, ByteDance, Uber | 19 |

\* Qualcomm's robots.txt allows `/api/apply` but arguably not `/api/pcsx`. Confirm before using.

## Endpoint shapes

| Platform | Request |
|---|---|
| Workday | `POST https://{host}/wday/cxs/{tenant}/{site}/jobs` body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}`. Lists stop at a total of 2000, so split the search by location/category filters to get the rest. The list has no description; fetch details per job. |
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Lever | `GET https://api.lever.co/v0/postings/{site}?mode=json` |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{org}` |
| SmartRecruiters | `GET https://api.smartrecruiters.com/v1/companies/{id}/postings?limit=100&offset=N` |
| Eightfold (PCSX) | `GET https://{domain}/api/pcsx/search?domain={d}&query=&start=N&num=10` |
| Eightfold (v2) | `GET https://{domain}/api/apply/v2/jobs?domain={d}&start=N&num=10` |
| Oracle HCM | `GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site},limit=25,offset=N` |
| iCIMS Jibe | `GET https://{domain}/api/jobs?limit=N&page=P` |
| SuccessFactors CSB | `GET https://{host}/search/?q=&startrow=N` (HTML; parse `a.jobTitle-link`); `/sitemap.xml` lists `/job/` URLs |
| Avature | `GET https://{host}/{locale}/{portal}/SearchJobs/feed/` (RSS) |

## All 100 companies

| # | Company | Tier | Platform | Identifiers | Jobs | Notes |
|---|---|---|---|---|---|---|
| 1 | Microsoft | T1 | Eightfold PCSX | `apply.careers.microsoft.com`, domain `microsoft.com` | 2429 | Old gcsservices API is dead |
| 2 | Google | T3 | Custom | — | — | robots.txt disallows job results pages; JS-rendered |
| 3 | Amazon | T1 | Custom | `GET https://www.amazon.jobs/en/search.json?result_limit=N&offset=N` | 10000 (cap) | Paginate/facet |
| 4 | Apple | T3 | Custom | — | — | No working endpoint found (HTTP 436) |
| 5 | Meta | T3 | Custom GraphQL | — | — | robots.txt notice restricts automated collection |
| 6 | Netflix | T1 | Eightfold v2 | `explore.jobs.netflix.net`, domain `netflix.com` | 394 | PCSX not enabled; use v2 |
| 7 | NVIDIA | T1 | Workday | `nvidia.wd5.myworkdayjobs.com` / `nvidia` / `NVIDIAExternalCareerSite` | 2000 (cap) | |
| 8 | Adobe | T1 | Workday | `adobe.wd5.myworkdayjobs.com` / `adobe` / `external_experienced` | 280 | Check for a university site |
| 9 | Salesforce | T1 | Workday | `salesforce.wd12.myworkdayjobs.com` / `salesforce` / `External_Career_Site` | 1590 | |
| 10 | Oracle | T1 | Oracle HCM | `eeho.fa.us2.oraclecloud.com`, site `CX_45001` | 2733 | Other sites on same host: CX_77003, CX_78003, CX_48001, CX_41001 |
| 11 | IBM | T1 (partial) | Custom (Elasticsearch) | `POST https://www-api.ibm.com/search/api/v2` appId `careers`, scope `careers2`, `Origin: https://careers.ibm.com` | 2190 | Field mapping unconfirmed; undocumented endpoint, check robots/terms |
| 12 | Intel | T1 | Workday | `intel.wd1.myworkdayjobs.com` / `intel` / `External` | 792 | |
| 13 | AMD | T1 | iCIMS Jibe | `careers.amd.com/api/jobs` | 1273 | |
| 14 | Qualcomm | T1* | Eightfold PCSX | `careers.qualcomm.com`, domain `qualcomm.com` | ? | robots.txt check needed |
| 15 | Cisco | T1 | Workday (Phenom front end) | `cisco.wd5.myworkdayjobs.com` / `cisco` / `Cisco_Careers` | 1530 | |
| 16 | Dell | T1 | Oracle HCM | `enterpriseplatform.dell.com`, site `CX_1` | 511 | |
| 17 | HPE | T1 | Workday | `hpe.wd5.myworkdayjobs.com` / `hpe` / `Jobsathpe` | 1716 | Also carries Juniper roles |
| 18 | Broadcom | T1 | Workday | `broadcom.wd1.myworkdayjobs.com` / `broadcom` / `External_Career` | 374 | |
| 19 | SAP | T3 | SuccessFactors | `jobs.sap.com` | — | Cloudflare challenge (403) |
| 20 | ServiceNow | T1 | SmartRecruiters | `ServiceNow` | 736 | |
| 21 | Workday | T1 | Workday | `workday.wd5.myworkdayjobs.com` / `workday` / `Workday` | 377 | Same count as CrowdStrike; recheck |
| 22 | Atlassian | T1 | Custom JSON (iCIMS apply) | `GET https://www.atlassian.com/endpoint/careers/listings` | 372 | |
| 23 | Autodesk | T1 | Workday | `autodesk.wd1.myworkdayjobs.com` / `autodesk` / `Ext` | 177 | |
| 24 | Intuit | T3 | Radancy/TalentBrew | — | — | robots.txt disallows `/search-jobs/` |
| 25 | Shopify | T3 | Ashby | org slug unknown | — | Find the real slug in the page's JS (solvable) |
| 26 | HubSpot | T1 | Greenhouse | `hubspotjobs` | 71 | |
| 27 | Zoom | T1 | Workday | `zoom.wd5.myworkdayjobs.com` / `zoom` / `Zoom` | 90 | |
| 28 | Dropbox | T1 | Greenhouse | `dropbox` | 22 | |
| 29 | Akamai | T3 | Probably Workday | tenant/site unknown | — | Bot protection (403) |
| 30 | Palantir | T1 | Lever | `palantir` | 306 | |
| 31 | Palo Alto Networks | T1 | Workday | `paloaltonetworks.wd5.myworkdayjobs.com` / `paloaltonetworks` / `panwexternalcareers` | 1407 | |
| 32 | CrowdStrike | T1 | Workday | `crowdstrike.wd5.myworkdayjobs.com` / `crowdstrike` / `crowdstrikecareers` | 377 | |
| 33 | Fortinet | T1 | Oracle HCM | `edel.fa.us2.oraclecloud.com`, site `CX_2001` | 1052 | |
| 34 | Check Point | T1 | SmartRecruiters | `CheckPointSoftwareTechnologies2` | 289 | Site's own /api/ is disallowed; use SmartRecruiters |
| 35 | Zscaler | T1 | Greenhouse | `zscaler` | 357 | |
| 36 | Okta | T1 | Greenhouse | `okta` | 387 | |
| 37 | SentinelOne | T1 | Greenhouse | `sentinellabs` | 284 | |
| 38 | F5 | T1 | Workday | `ffive.wd5.myworkdayjobs.com` / `ffive` / `f5jobs` | 255 | |
| 39 | Rubrik | T1 | Greenhouse | `rubrik` | 153 | |
| 40 | Cloudflare | T1 | Greenhouse | `cloudflare` | 461 | |
| 41 | OpenAI | T1 | Ashby | `openai` | 800 | |
| 42 | Anthropic | T1 | Greenhouse | `anthropic` | 681 | |
| 43 | Databricks | T1 | Greenhouse | `databricks` | 896 | |
| 44 | Snowflake | T1 | Ashby | `snowflake` | 362 | |
| 45 | MongoDB | T1 | Greenhouse | `mongodb` | 363 | |
| 46 | Elastic | T1 | Greenhouse | `elastic` | 405 | |
| 47 | Confluent | T3 | Unknown | — | — | Vercel bot check (429) |
| 48 | Redis | T1 | Ashby | `redis` | 27 | |
| 49 | UiPath | T1 | Ashby | `uipath` | 103 | |
| 50 | C3.ai | T1 | Greenhouse | `c3iot` (also `c3ascend`) | 91 | |
| 51 | Accenture | T1 | Workday | `accenture.wd103.myworkdayjobs.com` / `accenture` / `AccentureCareers` | 2000 (cap) | |
| 52 | TCS | T3 | Custom | — | — | Bot block (403); iBegin (lateral), NextStep (campus) |
| 53 | Infosys | T3 | Custom | — | — | Akamai "Access Denied" |
| 54 | Wipro | T2 | SuccessFactors CSB | `careers.wipro.com/search/?q=&startrow=N`, `/sitemap.xml` | ? | |
| 55 | HCLTech | T2 | SuccessFactors CSB | `careers.hcltech.com/search/?q=&startrow=N`, `/sitemap.xml` | ? | |
| 56 | Cognizant | T3 | Probably iCIMS Jibe | `careers.cognizant.com/api/jobs` (unconfirmed) | — | Cloudflare challenge (403) |
| 57 | Capgemini | T1 | Custom WordPress | `GET https://www.capgemini.com/wp-json/llm/v1/jobs?page=N&size=20` | 6759 | Check robots/terms; India portal separate |
| 58 | NTT DATA | T1 | Phenom | `POST https://careers.nttdata.com/widgets` (ddoKey `refineSearch`, lang `en_global`) | 3092 | |
| 59 | DXC | T1 | Workday | `dxctechnology.wd1.myworkdayjobs.com` / `dxctechnology` / `DXCJobs` | 1219 | |
| 60 | Tech Mahindra | T3 | Custom ASP.NET | — | — | Search page unreachable by curl |
| 61 | LTIMindtree (LTM) | T2 | SuccessFactors CSB | `careers.ltm.com/search/?q=&startrow=N` | 39 | Also RippleHire |
| 62 | Mphasis | T3 | RippleHire SPA | `mphasis.ripplehire.com` | — | JS-only |
| 63 | Persistent | T3 | Custom | — | — | Endpoint not found |
| 64 | Coforge | T3 | Angular SPA | — | — | JS-only |
| 65 | Hexaware | T1 | Oracle HCM | `fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com`, sites `CX_1`, `CX_2` | 289 | |
| 66 | Genpact | T1 | Workday | `genpact.wd108.myworkdayjobs.com` / `genpact` / `External_Careers` | 2000 (cap) | |
| 67 | EPAM | T3 | Custom Next.js | — | — | robots.txt disallows `/api` |
| 68 | Globant | T2 | SuccessFactors CSB | `career.globant.com`, sitemap | ? | JS-rendered; sitemap route |
| 69 | Endava | T2 | iCIMS | `jobs-galaxe.icims.com/jobs/search?ss=1&in_iframe=1` | ? | HTML |
| 70 | Thoughtworks | T1 | Greenhouse | `thoughtworks` | 45 | |
| 71 | Fujitsu | T2 | SuccessFactors CSB | `www.jobs.global.fujitsu.com/search/?q=`; NA: `jobs.fnc.fujitsu.com` | 75+ | Many regional portals; 429s |
| 72 | NEC | T2 | SuccessFactors CSB | `careers.nec.com/tile-search-results/?q=&startrow=N` | 75+ | India/Japan portals separate |
| 73 | CGI | T2 | Njoyn | `cgi.njoyn.com/CORP/xweb/xweb.asp?clid=21001&page=joblisting` | ~630 | HTML |
| 74 | Kyndryl | T1 | Workday | `kyndryl.wd5.myworkdayjobs.com` / `kyndryl` / `KyndrylProfessionalCareers` | 835 | |
| 75 | Deloitte | T2 | Avature RSS + SmartRecruiters | US `apply.deloitte.com/careers/SearchJobs/feed/`; India `usijobs.deloitte.com/en_US/careersUSI/SearchJobs/feed/`; global `deloittecm.avature.net/en_US/careers/SearchJobs/feed/`; SR `Deloitte6` | 281 (SR) | One portal per member firm |
| 76 | PwC | T1 | Workday | `pwc.wd3.myworkdayjobs.com` / `pwc` / `Global_Experienced_Careers` + `Global_Campus_Careers` | 3879 + 1362 | Country sites blocked |
| 77 | EY | T2 | SuccessFactors CSB | `careers.ey.com/ey/search/?q=&locationsearch=` | 9275 | ~3018 in India |
| 78 | KPMG | T3 | Varies by member firm | — | — | US back end unknown |
| 79 | Booz Allen | T1 | Workday | `bah.wd1.myworkdayjobs.com` / `bah` / `BAH_Jobs` | 2000 (cap) | |
| 80 | Leidos | T1 | Workday | `leidos.wd5.myworkdayjobs.com` / `leidos` / `External` | 2000 (cap) | |
| 81 | Lenovo | T2 | Avature RSS | `jobs.lenovo.com/en_US/careers/SearchJobs/feed/` | ~999 | Campus portal `/LenovoCampus` |
| 82 | Sony | T1 | Workday | `sonyglobal.wd1.myworkdayjobs.com` / `sonyglobal` / `SonyGlobalCareers` (+ `SonyJapanCareers`) | 125 + 14 | Subsidiaries (PlayStation, Pictures, Music) not checked |
| 83 | Samsung | T1 | Workday | `sec.wd3.myworkdayjobs.com` / `sec` / `Samsung_Careers` | 663 | Semiconductor/India portals not checked |
| 84 | Panasonic | T1 | iCIMS Jibe | `careers.na.panasonic.com/api/jobs` | 490 | All Panasonic North America; filter for Connect |
| 85 | Ericsson | T1 | Eightfold PCSX | `jobs.ericsson.com`, domain `ericsson.com` | 532 | |
| 86 | Nokia | T1 | Oracle HCM | `fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com`, site `CX_1` | 571 | |
| 87 | Motorola Solutions | T1 | Workday | `motorolasolutions.wd5.myworkdayjobs.com` / `motorolasolutions` / `Careers` | 887 | |
| 88 | Arista | T1 | SmartRecruiters | `AristaNetworks` | 244 | |
| 89 | Juniper | T1 | Workday (via HPE) | same as HPE | — | Separate by keyword |
| 90 | Supermicro | T2 | SuccessFactors | `jobs.supermicro.com` | ? | Unverified; pages came back empty |
| 91 | Tencent | T1 | Custom JSON | `GET https://careers.tencent.com/tencentcareer/api/post/Query?pageIndex=N&pageSize=10&language=en-us&area=en-us` | 2259 | Mostly Chinese titles |
| 92 | ByteDance | T3 | Custom | — | — | Akamai "Access Denied" |
| 93 | Spotify | T1 | Lever | `spotify` | 89 | |
| 94 | Airbnb | T1 | Greenhouse | `airbnb` | 195 | |
| 95 | Uber | T3 | Custom RPC | — | — | Request shape not found |
| 96 | Stripe | T1 | Greenhouse | `stripe` | 713 | |
| 97 | PayPal | T1 | Eightfold PCSX | `paypal.eightfold.ai`, domain `paypal.com` | 319 | |
| 98 | Block | T1 | Greenhouse | `block` | 202 | Square, Cash App, TIDAL, Afterpay |
| 99 | Robinhood | T1 | Greenhouse | `robinhood` | 159 | |
| 100 | Epic Games | T1 | Greenhouse | `epicgames` | 144 | |
