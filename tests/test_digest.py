import asyncio
import json
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from sqlalchemy import select
from app import digest
from app.config import settings
from app.db import SessionLocal
from app.enrich import enrich_job, refresh_groups
from app.models import Job


@pytest.fixture
def telegram(fresh_db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:SECRET")
    monkeypatch.setattr(settings, "telegram_chat_id", "@fresher_jobs")
    monkeypatch.setattr(settings, "dashboard_url", "https://jobs.example.com")
    monkeypatch.setattr(settings, "digest_countries", "")
    monkeypatch.setattr(settings, "digest_max_jobs", 40)
    monkeypatch.setattr(digest, "SECONDS_BETWEEN_MESSAGES", 0)
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    return sent, handler


def add_jobs(*specs, first_seen=None):
    now = first_seen or datetime.now(timezone.utc)
    with SessionLocal() as db:
        for i, (title, location) in enumerate(specs):
            job = Job(source_provider="fake", source_key="fake:x", source_job_id=f"{title}-{i}", company="Acme",
                      title=title, location=location, apply_url=f"https://acme.example/jobs/{i}?a=1&b=2",
                      first_seen_at=now, last_seen_at=now, active=True)
            enrich_job(job)
            db.add(job)
        db.commit()
        refresh_groups(db)


def run(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return asyncio.run(digest.run_digest(client=client, **kwargs))


def pending_titles():
    with SessionLocal() as db:
        return sorted(j.title for j in db.scalars(select(Job).where(Job.notified_at.is_(None))))


def test_digest_sends_fresher_it_jobs_and_marks_everything(telegram):
    sent, handler = telegram
    add_jobs(("Software Engineering Intern", "Pune, India"), ("Graduate Data Analyst <AI>", "Bengaluru, India"),
             ("Senior Software Engineer", "Pune, India"), ("Account Executive Intern", "London, UK"))

    result = run(handler)

    assert result["status"] == "sent" and result["jobs_announced"] == 2 and result["jobs_skipped"] == 2
    assert len(sent) == 1
    message = sent[0]
    assert message["chat_id"] == "@fresher_jobs" and message["parse_mode"] == "HTML"
    text = message["text"]
    assert "2 new fresher-friendly IT jobs" in text
    assert "Software Engineering Intern" in text and "Graduate Data Analyst &lt;AI&gt;" in text
    assert "Senior Software Engineer" not in text and "Account Executive" not in text
    # Each job links to its FirstOffer page (details, Apply, Save, Share), not straight to the careers site.
    with SessionLocal() as db:
        intern_id = db.scalar(select(Job.id).where(Job.title == "Software Engineering Intern"))
    assert f'<a href="https://jobs.example.com/job/{intern_id}">Software Engineering Intern</a>' in text
    assert "acme.example" not in text
    assert "https://jobs.example.com/?experience=" in text
    assert text.index("Internships") < text.index("Fresher / entry level")
    assert pending_titles() == []

    # Nothing new: nothing is sent.
    assert run(handler)["jobs_announced"] == 0 and len(sent) == 1


def test_dry_run_sends_nothing_and_marks_nothing(telegram):
    sent, handler = telegram
    add_jobs(("Graduate Engineer Trainee", "Chennai, India"))
    result = run(handler, dry_run=True)
    assert result["status"] == "dry_run" and result["would_send"] == 1
    assert "Graduate Engineer Trainee" in result["messages"][0]
    assert sent == [] and pending_titles() == ["Graduate Engineer Trainee"]


def test_not_configured_does_nothing(telegram, monkeypatch):
    _, handler = telegram
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    add_jobs(("Graduate Engineer Trainee", "Chennai, India"))
    assert run(handler)["status"] == "not_configured"
    assert pending_titles() == ["Graduate Engineer Trainee"]


def test_old_jobs_and_other_countries_are_skipped(telegram, monkeypatch):
    sent, handler = telegram
    monkeypatch.setattr(settings, "digest_countries", "India")
    add_jobs(("Junior Developer", "Pune, India"), ("Junior Developer", "Austin, TX, United States"))
    add_jobs(("Software Engineering Intern", "Pune, India"), first_seen=datetime.now(timezone.utc) - timedelta(days=3))
    result = run(handler)
    assert result["jobs_announced"] == 1
    assert "Pune" in sent[0]["text"] and "Austin" not in sent[0]["text"] and "Intern" not in sent[0]["text"]
    assert pending_titles() == []


def test_long_digest_is_split_and_capped(telegram, monkeypatch):
    sent, handler = telegram
    monkeypatch.setattr(settings, "digest_max_jobs", 60)
    add_jobs(*[(f"Software Engineering Intern {'x' * 60} {i}", f"City{i}, India") for i in range(80)])
    result = run(handler)
    assert result["status"] == "sent" and result["jobs_announced"] == 80
    assert len(sent) > 1 and all(len(m["text"]) <= 4096 for m in sent)
    assert sent[0]["text"].endswith(f"(1/{len(sent)})</i>")
    assert "…and 20 more" in sent[-1]["text"]
    assert pending_titles() == []


def test_failure_halfway_keeps_unsent_jobs_pending(telegram, monkeypatch):
    sent, _ = telegram
    monkeypatch.setattr(settings, "digest_max_jobs", 80)
    add_jobs(*[(f"Software Engineering Intern {'x' * 60} {i}", f"City{i}, India") for i in range(80)])

    def handler(request):
        if sent:
            return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    result = run(handler)
    assert result["status"] == "error" and "chat not found" in result["error"]
    assert "SECRET" not in result["error"]
    assert result["messages_sent"] == 1
    remaining = pending_titles()
    assert 0 < len(remaining) < 80
    # Jobs in the message that went out are not announced again.
    assert not any(t in sent[0]["text"] for t in remaining)


def test_rate_limit_is_retried(telegram, monkeypatch):
    sent, _ = telegram
    real_sleep = asyncio.sleep
    monkeypatch.setattr("app.telegram.asyncio.sleep", lambda _seconds: real_sleep(0))
    add_jobs(("Graduate Engineer Trainee", "Chennai, India"))
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 1}})
        return httpx.Response(200, json={"ok": True})

    assert run(handler)["status"] == "sent" and len(calls) == 2


def test_digest_links_to_careers_site_without_public_address(telegram, monkeypatch):
    sent, handler = telegram
    monkeypatch.setattr(settings, "dashboard_url", "")
    add_jobs(("Software Engineering Intern", "Pune, India"))
    run(handler)
    assert 'href="https://acme.example/jobs/0?a=1&amp;b=2"' in sent[0]["text"]
