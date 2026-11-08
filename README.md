# FirstOffer
**Fresher IT jobs straight from company careers pages.**

A FastAPI service that collects open jobs from IT companies' official careers sites, stores them in one database, and serves them through an API for a dashboard and a Telegram digest.

Instead of one scraper per company, it has **one connector per hiring platform**. Most large companies run their careers site on a shared platform (Workday, Greenhouse, Eightfold, …) that serves job data as JSON, so adding a company is one line in `sources.json`.

`sources.json` holds 82 job boards covering 78 of the 100 target companies (79 including Juniper, whose jobs are on HPE's board). The other 21 are in `link_only.json`: we can't collect their jobs automatically (bot protection, robots.txt, or no public feed), so the dashboard links to their careers pages instead. [docs/company_sources.md](docs/company_sources.md) has the research behind every company.

## Connectors

**Hiring platforms**

| Provider | Settings in `sources.json` | Notes |
|---|---|---|
| `workday` | `host`, `tenant`, `site` | Searches stop at 2000 results, so big boards are split by the board's own filters. Descriptions come from per-job detail calls. |
| `greenhouse` | `board_token` | |
| `lever` | `site` | |
| `ashby` | `org` | |
| `smartrecruiters` | `company_id` | Descriptions from detail calls |
| `eightfold` | `host`, `domain`, `api` (`pcsx` or `v2`) | Descriptions from detail calls |
| `oracle` | `host`, `site`, optional `public_host` | Full descriptions from detail calls |
| `jibe` | `host`, optional `job_path` | iCIMS Jibe sites (`/api/jobs`) |
| `phenom` | `host`, `lang`, `country`, `job_url_prefix` | Phenom sites' own search endpoint |
| `successfactors` | `host`, optional `search_path` | Classic SuccessFactors sites that render search results as HTML |
| `njoyn` | `host`, `path`, `clid` | Njoyn/Cegid listings (CGI) |
| `sitemap` | `sitemap`, optional `job_pattern`, `details` | Sites whose only crawlable listing is the sitemap. Titles come from job URLs until the job page is read; `"details": false` skips reading pages for sites that need JavaScript (Wipro, HCLTech, Fujitsu) or have unreliable page titles (Lenovo). |

**Company-specific careers APIs:** `amazon` (split by country and business category, since one search stops at 10,000), `capgemini`, `tencent`, `atlassian`. Each takes a `host`.

Any source can also set `"interval_hours"` (default `POLL_INTERVAL_HOURS`) and `"enabled": false`.

## How polling works
- The scheduler wakes every `SCHEDULER_TICK_MINUTES` and polls only the sources that are due.
- Requests to a single host are spaced at least `MIN_REQUEST_INTERVAL_SECONDS` apart and retried with backoff on 429/5xx errors.
- **First poll of a source = silent seed run.** Its jobs are stored but never announced, so adding a company doesn't flood alerts.
- A job missing from `MISSED_RUNS_BEFORE_INACTIVE` complete polls in a row is marked closed. If a listing was cut short (for example by a cap), nothing is closed.
- For platforms whose job lists leave out the description, up to `DETAIL_FETCHES_PER_RUN` details are fetched per source per run, newest first. Large boards fill in over a few runs.
- Every run is logged in `source_runs`, and `/sources` shows each source's health.

## Run locally (Python 3.11+)
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env   # Windows; use cp on macOS/Linux
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for the API.

## Dashboard (React + Vite, Node 18+)
`dashboard/` is the job board: search, filters (experience, job type, country, remote, posted date, company), a "Freshers & interns" shortcut, job details with an Apply link to the official careers site, a Companies page (including link-only companies) and a source-health page. Filters live in the URL, so any search can be bookmarked or shared.

Public-site features:
- **Shareable job links**: every job has its own page at `/job/<id>`. The Share button copies the link or sends it to WhatsApp, Telegram, LinkedIn, X or email (on phones it opens the phone's own share sheet). The server fills in the page's title and preview tags, so a pasted link shows the job title, company and place in chat apps. "Share this search" copies a link to the current filters.
- **Apply**: opens the job on the company's own careers site, then offers to mark the job as applied.
- **My jobs**: visitors can save jobs (☆) and track each one as Saved, Applied, Interviewing, Got an offer or Not selected, add notes, and export the list as CSV. The list is kept in the visitor's own browser; there are no accounts.
- **Search engines**: job pages carry schema.org `JobPosting` data, and `/sitemap.xml` and `/robots.txt` list the open jobs so Google can find them. Set `DASHBOARD_URL` so the links use your public address.
- **Also**: a "New" badge for jobs added in the last 24 hours, a light/dark switch, "/" to jump to search, and a "Join Telegram" button (`TELEGRAM_CHANNEL_URL`, or leave it empty to hide the button).

Build it once and FastAPI serves it at http://127.0.0.1:8000/:
```bash
cd dashboard
npm install
npm run build
```
While working on the dashboard, run `npm run dev` (http://localhost:5173, hot reload) next to `uvicorn`. Vite forwards the API calls to port 8000.

Running `uvicorn` also starts the scheduler, which polls due sources every `SCHEDULER_TICK_MINUTES`.

Poll from the command line:
```bash
python -m app.poller --force                 # every source now
python -m app.poller --force --only nvidia   # sources whose company or key matches
python -m app.poller                         # only sources that are due
```

Run the tests:
```bash
python -m pytest -q
```

## Deploy (free)
Runs 24/7 on **Render**'s free tier with a **Supabase** free Postgres database and a free keep-awake pinger. Step-by-step: [docs/deploy_render.md](docs/deploy_render.md).
- `Dockerfile` builds the dashboard and the app into one image. `render.yaml` is a ready-made Render Blueprint.
- `STORE_DESCRIPTIONS=false` (lite storage) keeps the database small: descriptions are used to detect the experience level, then dropped.
- `PRUNE_CLOSED_AFTER_DAYS` deletes old closed jobs. `ALERT_CHAT_ID` gets a Telegram alert when a source keeps failing.
- `python -m app.copy_db --to <database URL> --lite` copies existing jobs into a new database.

## Telegram digest
Every hour the app posts one Telegram message listing newly found internship, fresher and junior IT jobs, each linked to its official apply page. Jobs are never announced twice, and backlog from a company's first poll is never announced. Setup takes about 5 minutes: see [docs/telegram_setup.md](docs/telegram_setup.md). Preview anytime with `python -m app.digest --dry-run`.

## Job tagging
Every job gets derived fields, computed by rules in `app/classify.py`, `app/locations.py` and `app/enrich.py`:
- **experience_level:** `intern`, `fresher` (0–1 yr), `junior` (1–3), `mid` (3–6), `senior` (6+), `leadership`, or empty when the posting doesn't say. Title words come first (Intern, Graduate, Trainee, New Grad, Engineer I, Senior, Staff, Director…), then the years of experience the description asks for.
- **category:** `software`, `data_ai`, `devops_cloud`, `security`, `qa_testing`, `hardware_embedded`, `networking`, `it_support`, `consulting_tech`, `product_design`, `non_it`, or `other` when the title is too vague to place.
- **city / country / countries / is_remote**, parsed from free-form locations such as "Noida, UP, IN, 201301" or "US-CA-Menlo Park".
- **dedup_key:** company + normalized title + place. Re-posts of the same opening are shown as one result, with `similar_count` giving the number of postings.

These are heuristics. Jobs they can't place stay empty or "other" rather than being guessed. After changing the rules, bump `ENRICH_VERSION` in `app/enrich.py` and run `python -m app.enrich`. The poller also re-tags each job the next time it sees it.

## API
- `GET /jobs` returns `{total, items}` for active jobs, newest first. Filters:
  - `q`: words matched as prefixes in title, company, location, department or category (SQLite full-text index)
  - `experience`: comma list, e.g. `intern,fresher,junior` (plus `unspecified`)
  - `category`: comma list; or `it_only=true` to hide clearly non-IT roles
  - `country` (comma list), `city`, `remote`, `company` (comma list), `posted_within_days`, `provider`
  - `collapse` (default `true`), `sort` (`newest` or `first_seen`), `limit`, `offset`
- `GET /jobs/{id}` returns one job with its description and the other postings of the same opening.
- `GET /filters` returns filter values with open-job counts for the dashboard menus (cached for 10 minutes).
- `GET /companies` lists every tracked company: the ones we collect (with open-job counts) and the link-only ones (with careers and fresher-portal links).
- `GET /stats` returns job and company counts. `GET /sources` returns per-source health: last success, job count, consecutive failures, last error.
- `POST /admin/digest` previews the Telegram digest (`?dry_run=false` sends it).
- `POST /admin/poll?force=true&only=...` triggers a poll. It needs the `X-Admin-Token` header to match `ADMIN_TOKEN`, and is disabled while `ADMIN_TOKEN` is empty.

## Database
SQLite by default; set `DATABASE_URL=postgresql+psycopg://...` for Postgres (text search then falls back to `ILIKE`). There are no migrations yet: on startup, new nullable columns are added to existing tables automatically. For other schema changes, delete `jobs.db` and re-poll.

## Rules we follow
- Only public job listings, through the same endpoints the official careers pages use. Respect robots.txt and each site's terms.
- No tooling to get around bot protection or CAPTCHAs. Sites that block automated access are shown as link-only (see the research doc).
- Poll gently: at most about 1 request per second per site, and a few polls per day.
