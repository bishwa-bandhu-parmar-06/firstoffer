"""Hourly Telegram digest of newly found fresher-friendly IT jobs.

Every job starts with notified_at empty (except backlog from a source's first poll, which is marked at
once). Each digest run looks at those jobs, sends the ones that match the digest settings, and marks
all of them as handled so nothing is announced twice.

    python -m app.digest --dry-run   # print what would be sent
    python -m app.digest             # send (needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
"""
import argparse
import asyncio
import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import httpx
from sqlalchemy import select
from app.classify import IT_CATEGORIES
from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Job, as_utc
from app.telegram import SECONDS_BETWEEN_MESSAGES, TelegramError, send_message

# Telegram's limit is 4096 characters; leave room for the "part 2/3" suffix.
MAX_MESSAGE_CHARS = 3800
SECTIONS = [
    ("intern", "🎓 <b>Internships</b>"),
    ("fresher", "🌱 <b>Fresher / entry level</b>"),
    ("junior", "📈 <b>Junior (1–3 yrs)</b>"),
    ("mid", "💼 <b>Mid level</b>"),
    ("senior", "🧭 <b>Senior</b>"),
    ("leadership", "🏛 <b>Leadership</b>"),
]

_digest_lock = asyncio.Lock()


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Selection:
    to_send: list[Job] = field(default_factory=list)
    # Pending jobs that don't match the digest settings; marked as handled without being announced.
    to_skip: list[Job] = field(default_factory=list)


def is_eligible(job: Job, now: datetime) -> bool:
    countries = _list(settings.digest_countries)
    first_seen = as_utc(job.first_seen_at)
    return (
        job.active
        and job.is_primary is not False
        and job.experience_level in _list(settings.digest_experience)
        # Same rule as the dashboard's "Hide non-IT jobs": unclassified titles stay in.
        and (job.category in IT_CATEGORIES or job.category in (None, "other"))
        and first_seen is not None and first_seen >= now - timedelta(hours=settings.digest_max_age_hours)
        and (not countries or any(f"|{c}|" in (job.countries or "") for c in countries))
    )


def select_jobs(db, now: datetime) -> Selection:
    selection, seen_openings = Selection(), set()
    pending = db.scalars(select(Job).where(Job.notified_at.is_(None)).order_by(Job.first_seen_at, Job.id))
    for job in pending:
        # One line per opening, even if it was posted several times in this batch.
        if is_eligible(job, now) and (job.dedup_key is None or job.dedup_key not in seen_openings):
            selection.to_send.append(job)
            seen_openings.add(job.dedup_key)
        else:
            selection.to_skip.append(job)
    return selection


def _place(job: Job) -> str:
    place = ", ".join(p for p in (job.city, job.country) if p)
    if not place:
        # The raw location of remote jobs is often just "Remote" or "Distributed".
        return "Remote" if job.is_remote else (job.location or "Location not listed")
    return place + (" · Remote" if job.is_remote else "")


def _audience() -> str:
    levels = set(_list(settings.digest_experience))
    return "fresher-friendly IT" if levels <= {"intern", "fresher", "junior"} else "IT"


def job_link(job: Job) -> str:
    """The job's FirstOffer page (details, Apply, Save, Share) when the site has a public address,
    otherwise the company's own posting."""
    if settings.dashboard_url and job.id is not None:
        return f"{settings.dashboard_url.rstrip('/')}/job/{job.id}"
    return job.apply_url


def _job_line(job: Job) -> str:
    title = html.escape(job.title.strip())
    url = html.escape(job_link(job), quote=True)
    return f'• <a href="{url}">{title}</a> — {html.escape(job.company)} · {html.escape(_place(job))}'


def _dashboard_link(label: str) -> str:
    if not settings.dashboard_url:
        return ""
    params = {"experience": settings.digest_experience, "it_only": "true", "sort": "first_seen"}
    if settings.digest_countries:
        params["country"] = settings.digest_countries
    url = f"{settings.dashboard_url.rstrip('/')}/?{urlencode(params)}"
    return f'<a href="{html.escape(url, quote=True)}">{label}</a>'


def build_messages(jobs: list[Job]) -> list[tuple[str, list[Job]]]:
    """Split the digest into Telegram-sized messages. Returns [(text, jobs listed in it)]."""
    if not jobs:
        return []
    shown = jobs[:settings.digest_max_jobs]
    hidden = len(jobs) - len(shown)
    order = {level: i for i, (level, _) in enumerate(SECTIONS)}
    shown.sort(key=lambda j: (order.get(j.experience_level, 99), j.company.lower(), j.title.lower()))

    header = f"🆕 <b>{html.escape(settings.brand_name)} · {len(jobs)} new {_audience()} {'job' if len(jobs) == 1 else 'jobs'}</b>"
    if settings.digest_countries:
        header += f" in {html.escape(settings.digest_countries)}"
    blocks: list[tuple[str, Job | None]] = [(header, None)]
    for level, heading in SECTIONS:
        level_jobs = [j for j in shown if j.experience_level == level]
        if level_jobs:
            blocks.append((f"\n{heading}", None))
            blocks.extend((_job_line(j), j) for j in level_jobs)
    footer = []
    if hidden:
        more = _dashboard_link("see all on the dashboard")
        footer.append(f"\n…and {hidden} more" + (f": {more}" if more else "."))
    elif settings.dashboard_url:
        footer.append("\n" + _dashboard_link(f"Browse all {_audience()} jobs"))
    footer.append("<i>Experience levels are detected automatically. Check each posting before applying.</i>")
    blocks.extend((line, None) for line in footer)

    messages, text, listed = [], "", []
    for line, job in blocks:
        if text and len(text) + len(line) + 1 > MAX_MESSAGE_CHARS:
            messages.append((text, listed))
            text, listed = "", []
        text = f"{text}\n{line}" if text else line
        if job is not None:
            listed.append(job)
    messages.append((text, listed))
    if len(messages) > 1:
        messages = [(f"{t}\n\n<i>({i}/{len(messages)})</i>", js) for i, (t, js) in enumerate(messages, 1)]
    # Jobs beyond digest_max_jobs ride along with the last message, so they're marked when it succeeds.
    messages[-1][1].extend(jobs[settings.digest_max_jobs:])
    return messages


async def run_digest(dry_run: bool = False, client: httpx.AsyncClient | None = None) -> dict:
    configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    if not dry_run and not configured:
        return {"status": "not_configured", "detail": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"}
    if _digest_lock.locked():
        return {"status": "skipped", "detail": "a digest is already running"}
    async with _digest_lock:
        init_db()
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            selection = select_jobs(db, now)
            messages = build_messages(selection.to_send)
            if dry_run:
                return {"status": "dry_run", "would_send": len(selection.to_send), "would_skip": len(selection.to_skip),
                        "messages": [text for text, _ in messages]}

            sent_jobs, sent_messages, error = 0, 0, None
            own_client = client is None
            client = client or httpx.AsyncClient(timeout=30)
            try:
                for i, (text, jobs) in enumerate(messages):
                    if i:
                        await asyncio.sleep(SECONDS_BETWEEN_MESSAGES)
                    try:
                        await send_message(client, settings.telegram_bot_token, settings.telegram_chat_id, text)
                    except TelegramError as exc:
                        error = str(exc)
                        break
                    # Mark per message, so a failure halfway never re-announces what already went out.
                    for job in jobs:
                        job.notified_at = now
                    db.commit()
                    sent_jobs += len(jobs)
                    sent_messages += 1
            finally:
                if own_client:
                    await client.aclose()

            if error is None:
                for job in selection.to_skip:
                    job.notified_at = now
                db.commit()
            return {"status": "error" if error else "sent", "error": error, "messages_sent": sent_messages,
                    "jobs_announced": sent_jobs, "jobs_skipped": len(selection.to_skip) if error is None else 0}


def connection_test_message() -> str:
    return (f"✅ <b>{html.escape(settings.brand_name)} job alerts are connected.</b>\n"
            "New fresher-friendly IT jobs from company careers sites will be posted here every hour.")


async def send_connection_test() -> dict:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return {"status": "not_configured", "detail": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await send_message(client, settings.telegram_bot_token, settings.telegram_chat_id, connection_test_message())
        except TelegramError as exc:
            return {"status": "error", "error": str(exc)}
    return {"status": "sent", "chat": settings.telegram_chat_id}


def main():
    parser = argparse.ArgumentParser(description="Send (or preview) the Telegram digest of new fresher-friendly IT jobs.")
    parser.add_argument("--dry-run", action="store_true", help="print the messages instead of sending them")
    parser.add_argument("--test", action="store_true", help="only send a short 'connected' message to check the setup")
    args = parser.parse_args()
    if args.test:
        print(asyncio.run(send_connection_test()))
        return
    result = asyncio.run(run_digest(dry_run=args.dry_run))
    for text in result.pop("messages", []):
        print(text, end="\n\n" + "-" * 60 + "\n")
    print(result)


if __name__ == "__main__":
    main()
