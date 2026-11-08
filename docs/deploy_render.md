# Deploy for free: Render + Supabase + a keep-awake pinger

| Piece | What it does | Cost |
|---|---|---|
| **Render** (free web service) | Runs the app: dashboard, hourly job checks, Telegram digest | ₹0 |
| **Supabase** (free Postgres) | Stores the jobs, so a Render restart loses nothing | ₹0 |
| **cron-job.org** (free) | Opens the app every 10 minutes so Render never puts it to sleep | ₹0 |

About 30–40 minutes the first time. You need: a GitHub account (you have one), an email address, and your Telegram bot token.

---

## Step 1: Create the database on Supabase (10 min)
1. Go to **https://supabase.com** → **Start your project** → sign up (signing in with GitHub is easiest).
2. Click **New project**:
   - **Name:** `firstoffer`
   - **Database Password:** click **Generate a password** and **save it somewhere safe** (you need it in step 1.4).
   - **Region:** *South Asia (Mumbai)*, or *Southeast Asia (Singapore)*.
   - Plan: **Free**. Click **Create new project** and wait 1–2 minutes.
3. At the top of the project page, click **Connect**.
4. Under **Connection string**, choose **Session pooler** (not "Direct connection", which Render can't reach). Copy the URI. It looks like:
   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```
   Replace `[YOUR-PASSWORD]` with the password from step 1.2. This full line is your **DATABASE_URL**. Keep it private: it gives full access to the database.

## Step 2: Copy the jobs you already have into Supabase (5 min)
So the server starts with full history and doesn't re-announce anything. On your PC, in the project folder:
```bash
.venv\Scripts\python.exe -m app.copy_db --lite --to "PASTE-YOUR-DATABASE_URL-HERE"
```
It prints `copied 2000 jobs`, `copied 4000 jobs`, … and ends with `{'jobs': ...}`. Over a home connection this takes a few minutes.

## Step 3: Put the code on GitHub (5 min)
Render deploys from a GitHub repository. Create a **private** repository and push this project to it (Claude can do this for you).
`.env` (your token) and `jobs.db` are listed in `.gitignore`, so they are **not** uploaded.

## Step 4: Deploy on Render (10 min)
1. Go to **https://render.com** → **Get Started** → sign up with **GitHub**.
2. Allow Render to see your new repository when it asks.
3. In Render: **New +** → **Blueprint** → choose the repository → Render reads `render.yaml` and shows one service, **firstoffer**.
4. Fill in the values it asks for:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Supabase URI from step 1.4 |
   | `TELEGRAM_BOT_TOKEN` | your bot token (a fresh one if you used `/revoke` with BotFather) |
   | `TELEGRAM_CHAT_ID` | `-1004375964201` (your channel's permanent ID; keeps working if you rename the channel) |
   | `ALERT_CHAT_ID` | optional, see "Failure alerts" below; can be left empty |
   | `DASHBOARD_URL` | leave empty for now |
5. Click **Apply**. The first build takes 5–10 minutes. When it says **Live**, open the address Render shows, e.g. `https://firstoffer.onrender.com` (Render adds a few letters if that name is taken). You should see the job board.
6. Now set `DASHBOARD_URL`: service → **Environment** → `DASHBOARD_URL` = that address → **Save**. Render restarts the app, and the Telegram digest gets a "Browse all" link.

## Step 5: Keep it awake (5 min)
Without visits, Render's free tier sleeps after 15 minutes, which would stop the hourly checks.
1. Go to **https://cron-job.org** → sign up (free).
2. **Create cronjob**:
   - **URL:** `https://firstoffer.onrender.com/health` (your address + `/health`)
   - **Execution schedule:** every **10 minutes**
   - Save.
3. After 15 minutes, its history should show successful runs (status 200).

## Step 6: Stop the copy on your PC ⚠️
Once Render is live, **stop the app running on your PC** (press Ctrl+C in its terminal). Otherwise both copies post to your channel and every job appears twice.

---

## Failure alerts (optional)
To get a private Telegram message when a company's job feed fails 3 checks in a row:
1. Open your bot (`t.me/fresher_it_jobs_bot`) and send it any message, e.g. `hi`.
2. Open `https://api.telegram.org/bot<YOUR-TOKEN>/getUpdates` in a browser and find `"chat":{"id":123456789`. That number is your chat id.
3. In Render → Environment, set `ALERT_CHAT_ID` to that number.

## Everyday use
- **Update the app:** push changes to GitHub; Render rebuilds and redeploys automatically (about 1 minute of downtime).
- **Logs:** Render → service → **Logs** shows each check and digest.
- **Database size:** Supabase → **Project Settings → Usage**. Lite mode keeps it around 150–250 MB of the 500 MB free limit, because closed jobs are deleted after 30 days.
- **Health of each company's feed:** the **Source health** tab on the dashboard.

## If something goes wrong
| Problem | Fix |
|---|---|
| Build fails on Render | Open the deploy log; most often a typo in an environment value. |
| `could not translate host name` / connection errors | Use the **Session pooler** URI from Supabase (step 1.4), and check that the password has no `[ ]` left in it. |
| `Ran out of memory` on Render | Set `MAX_CONCURRENT_SOURCES` to `1` in Render → Environment. |
| Nothing posted to Telegram | Normal in quiet hours. Check with the dashboard's "Freshers & interns" filter sorted by "Recently added here". |
| App asleep / dashboard slow to open | Check that the cron-job.org job is enabled and succeeding. |
| Supabase project paused | Only happens after a week with no activity: open Supabase and click **Restore**. |

**Limits to know:** Render may restart free services at any time (about 1 minute offline, no data lost), and Render or Supabase could change their free tiers. If Render's free tier stops working for you, change the plan to **Starter ($7/month)** in Render. Nothing else changes, and the pinger is no longer needed.
