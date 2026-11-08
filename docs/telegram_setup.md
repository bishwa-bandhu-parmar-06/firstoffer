# Telegram digest setup

Once an hour (at minute `DIGEST_MINUTE`), the app posts one message listing the IT jobs found since the last digest that suit freshers: internships, fresher/entry-level and junior roles. Every job is announced at most once. A company's first poll never produces an announcement, because those jobs were already open before the app started tracking.

## 1. Create the bot (2 minutes)
1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a display name (e.g. "Fresher IT Jobs") and a username ending in `bot` (e.g. `fresher_it_jobs_bot`).
3. BotFather replies with a **token** like `123456789:AA...`. Treat it like a password: anyone who has it can post as your bot.

## 2. Create the channel (or group)
A **channel** is the usual choice for a job feed: only the bot posts, and anyone can join and read.
1. Create a new channel. If it's **public**, its username (e.g. `@fresher_it_jobs`) is the chat id.
2. Open the channel → Administrators → Add admin → pick your bot → allow **Post messages**.

For a **group** or **private channel** you need the numeric id instead:
1. Add the bot (as admin for a channel), then post any message there.
2. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and look for `"chat":{"id":-100...`. That number, including the minus sign, is the chat id.

## 3. Configure the app
In `.env`:
```
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_CHAT_ID=@fresher_it_jobs
DASHBOARD_URL=https://your-dashboard-address   # optional; job links open FirstOffer job pages, plus a "browse all" link
```
Optional:
- `DIGEST_COUNTRIES=India`: only jobs in these countries (comma list; default is everywhere).
- `DIGEST_EXPERIENCE=intern,fresher,junior`: which levels to announce.
- `DIGEST_MAX_JOBS=40`: jobs listed per digest. The rest are summed up as "…and N more".
- `DIGEST_MAX_AGE_HOURS=24`: jobs first seen longer ago than this are never announced.

## 4. Test it
```bash
python -m app.digest --dry-run   # prints the message(s) that would be sent; changes nothing
python -m app.digest             # sends now and marks those jobs as announced
```
When `uvicorn app.main:app` runs with a token and chat id set, the digest goes out every hour automatically. `POST /admin/digest` (with `X-Admin-Token`) previews it, or sends it with `?dry_run=false`.

## Good to know
- Long digests are split into several messages under Telegram's 4096-character limit, sent a few seconds apart to stay within Telegram's posting limits for a single chat.
- If sending fails halfway (wrong chat id, bot not an admin), jobs already posted stay marked, and the rest are retried next hour. The error is returned and logged without the bot token.
- An hour with no new matching jobs sends nothing.
- Experience levels are detected automatically, so the message reminds readers to check each posting.
