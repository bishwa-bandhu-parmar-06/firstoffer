import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import poller
from app.connectors import CONNECTORS
from app.connectors.base import FetchResult, make_job
from app.db import SessionLocal
from app.models import Job, SourceRun, SourceState


class FakeConnector:
    KEY_FIELDS = ("board",)

    def __init__(self):
        self.ids: list[str] = []
        self.complete = True
        self.fail = False

    async def fetch_jobs(self, http, source):
        if self.fail:
            raise RuntimeError("board is down")
        jobs = [make_job(source_job_id=i, title=f"Job {i}", apply_url=f"https://x/{i}") for i in self.ids]
        return FetchResult(jobs, complete=self.complete)


@pytest.fixture
def fake(fresh_db, monkeypatch):
    connector = FakeConnector()
    monkeypatch.setitem(CONNECTORS, "fake", connector)
    source = {"company": "Acme", "provider": "fake", "board": "acme", "key": "fake:acme"}
    monkeypatch.setattr(poller, "load_sources", lambda: [source])
    return connector


def poll():
    return asyncio.run(poller.poll_all_sources(force=True))


def jobs_by_id():
    with SessionLocal() as db:
        return {j.source_job_id: j for j in db.scalars(select(Job))}


def test_first_poll_is_a_silent_seed_then_new_jobs_await_the_digest(fake):
    fake.ids = ["a", "b"]
    poll()
    # Backlog from the first poll is marked as handled, so the digest never announces it.
    assert all(j.notified_at is not None for j in jobs_by_id().values())

    fake.ids = ["a", "b", "c"]
    totals = poll()
    assert totals["new"] == 1
    assert jobs_by_id()["c"].notified_at is None


def test_job_closes_after_missing_twice_and_reopens(fake):
    fake.ids = ["a", "b"]
    poll()
    fake.ids = ["a"]
    poll()
    assert jobs_by_id()["b"].active and jobs_by_id()["b"].missed_runs == 1
    poll()
    assert not jobs_by_id()["b"].active
    fake.ids = ["a", "b"]
    poll()
    assert jobs_by_id()["b"].active and jobs_by_id()["b"].missed_runs == 0


def test_incomplete_listing_does_not_count_misses(fake):
    fake.ids = ["a", "b"]
    poll()
    fake.ids, fake.complete = ["a"], False
    poll()
    poll()
    assert jobs_by_id()["b"].active and jobs_by_id()["b"].missed_runs == 0


def test_failure_is_recorded_and_keeps_jobs(fake):
    fake.ids = ["a"]
    poll()
    fake.fail = True
    totals = poll()
    assert totals["errors"] == 1
    with SessionLocal() as db:
        state = db.get(SourceState, "fake:acme")
        assert state.consecutive_failures == 1 and "board is down" in state.last_error
        assert db.scalars(select(SourceRun).order_by(SourceRun.id.desc())).first().status == "error"
    assert jobs_by_id()["a"].active


def test_listing_does_not_overwrite_fields_read_from_detail_page(fake):
    fake.DETAIL_FIELDS = {"title"}
    fake.ids = ["a"]
    poll()
    with SessionLocal() as db:
        job = db.scalars(select(Job)).one()
        job.title = "Real Title From Page"
        job.details_fetched_at = datetime.now(timezone.utc)
        db.commit()
    poll()
    assert jobs_by_id()["a"].title == "Real Title From Page"


def test_is_due_respects_interval():
    now = datetime.now(timezone.utc)
    state = SourceState(key="k", provider="p", company="c", last_attempt_at=now - timedelta(hours=1))
    assert poller.is_due({"interval_hours": 3}, None, now)
    assert not poller.is_due({"interval_hours": 3}, state, now)
    state.last_attempt_at = (now - timedelta(hours=3)).replace(tzinfo=None)  # SQLite returns naive datetimes
    assert poller.is_due({"interval_hours": 3}, state, now)


def test_api_stats_and_admin_guard(fake):
    from app.main import app
    fake.ids = ["a", "b"]
    poll()
    client = TestClient(app)
    assert client.get("/stats").json() == {"total_jobs": 2, "active_jobs": 2, "companies_with_jobs": 1}
    assert client.post("/admin/poll").status_code == 403
    assert client.get("/sources").json()[0]["last_job_count"] == 2
