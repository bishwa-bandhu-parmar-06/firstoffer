import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects import postgresql
from app import alerts, poller
from app.config import settings
from app.connectors import CONNECTORS
from app.connectors.base import FetchResult, make_job
from app.copy_db import copy_database
from app.db import SessionLocal, normalize_database_url
from app.enrich import prune_closed_jobs, refresh_groups
from app.models import Job, SourceRun, SourceState
from app.search import JobFilters, conditions


class Board:
    KEY_FIELDS = ("board",)

    def __init__(self):
        self.jobs = []
        self.fail = False

    async def fetch_jobs(self, http, source):
        if self.fail:
            raise RuntimeError("HTTP 503 from board")
        return FetchResult([make_job(**j) for j in self.jobs])


@pytest.fixture
def board(fresh_db, monkeypatch):
    connector = Board()
    monkeypatch.setitem(CONNECTORS, "fake", connector)
    monkeypatch.setattr(poller, "load_sources", lambda: [{"company": "Acme", "provider": "fake", "board": "b", "key": "fake:b"}])
    return connector


def poll():
    return asyncio.run(poller.poll_all_sources(force=True))


def test_normalize_database_url():
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("sqlite:///./jobs.db") == "sqlite:///./jobs.db"


def test_lite_storage_tags_from_description_then_drops_it(board, monkeypatch):
    monkeypatch.setattr(settings, "store_descriptions", False)
    board.jobs = [dict(source_job_id="1", title="Java Developer", apply_url="https://x/1",
                       description="<p>We hire freshers: 0-1 years of experience.</p>")]
    poll()
    poll()  # a later listing repeating the description must not store it either
    with SessionLocal() as db:
        job = db.scalars(select(Job)).one()
        assert job.description is None
        assert job.experience_level == "fresher"


def test_prune_removes_only_long_closed_jobs(board):
    board.jobs = [dict(source_job_id=str(i), title=f"Job {i}", apply_url=f"https://x/{i}") for i in range(3)]
    poll()
    long_ago = datetime.now(timezone.utc) - timedelta(days=40)
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.source_job_id == "0").values(active=False, last_seen_at=long_ago))
        db.execute(update(Job).where(Job.source_job_id == "1").values(active=False))  # closed recently
        db.add(SourceRun(source_key="fake:b", provider="fake", company="Acme", started_at=long_ago, status="success"))
        db.commit()
        assert prune_closed_jobs(db, 30) == 1
        assert sorted(j.source_job_id for j in db.scalars(select(Job))) == ["1", "2"]
        assert all(r.started_at > long_ago.replace(tzinfo=None) for r in db.scalars(select(SourceRun)))
        assert prune_closed_jobs(db, 0) == 0


def test_alert_after_repeated_failures_and_on_recovery(board, monkeypatch):
    monkeypatch.setattr(settings, "alert_after_failures", 2)
    sent = []

    async def fake_send(results):
        sent.append([(r["company"], r["alert"]) for r in results])

    monkeypatch.setattr(poller, "send_source_alerts", fake_send)
    board.jobs = [dict(source_job_id="1", title="Job", apply_url="https://x/1")]
    poll()
    board.fail = True
    poll()
    poll()  # second failure in a row -> alert
    poll()  # third: no repeat alert
    board.fail = False
    poll()  # recovered
    alerts_sent = [batch for batch in sent if batch]
    assert alerts_sent == [[("Acme", "failing")], [("Acme", "recovered")]]


def test_alert_message_text():
    text = alerts.build_alert([
        {"company": "Acme <Corp>", "key": "fake:b", "error": "HTTP 503", "alert": "failing"},
        {"company": "Globex", "key": "fake:g", "error": None, "alert": "recovered"},
    ])
    assert "Acme &lt;Corp&gt;" in text and "HTTP 503" in text and "Working again:</b> Globex" in text
    assert alerts.build_alert([]) is None


def test_copy_database_to_new_target(board, tmp_path):
    board.jobs = [dict(source_job_id=str(i), title=f"Software Engineer {i}", apply_url=f"https://x/{i}",
                       description="<p>Long text</p>") for i in range(5)]
    poll()
    target = f"sqlite:///{tmp_path / 'copy.db'}"
    assert copy_database(target, lite=True, replace=False) == {"jobs": 5}
    engine = create_engine(target)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Job.__table__)) == 5
        assert conn.scalar(select(func.count()).select_from(Job.__table__).where(Job.description.is_not(None))) == 0
        assert conn.scalar(select(func.count()).select_from(SourceState.__table__)) == 1
    with pytest.raises(SystemExit):
        copy_database(target, lite=True, replace=False)
    assert copy_database(target, lite=False, replace=True) == {"jobs": 5}


def test_main_queries_compile_for_postgres(monkeypatch):
    # No Postgres server in the test run: at least check the SQL that differs by database compiles for it.
    monkeypatch.setattr("app.search.IS_SQLITE", False)
    dialect = postgresql.psycopg.dialect()
    filters = JobFilters(q="java pune", experience=["fresher", "unspecified"], it_only=True, country=["India"],
                         remote=True, posted_within_days=7)
    sql = str(select(Job.id).where(*conditions(filters)).order_by(Job.listed_at.desc().nulls_last())
              .compile(dialect=dialect))
    assert "ILIKE" in sql.upper() and "NULLS LAST" in sql.upper() and "jobs_fts" not in sql

    captured = []

    class Recorder:
        def execute(self, statement):
            captured.append(str(statement.compile(dialect=dialect)))

        def commit(self):
            pass

        def get_bind(self):
            return create_engine("postgresql+psycopg://u:p@localhost/db")

    refresh_groups(Recorder())
    assert "IS DISTINCT FROM" in captured[0] and "OVER (PARTITION BY" in captured[0]
