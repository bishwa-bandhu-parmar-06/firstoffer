import os
import tempfile

# Must run before anything imports app.config: point the app at a throwaway database
# and turn off the politeness delay and retries so tests are fast.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["MIN_REQUEST_INTERVAL_SECONDS"] = "0"
os.environ["HTTP_RETRIES"] = "0"
os.environ["ADMIN_TOKEN"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

import httpx
import pytest
from sqlalchemy import text
from app.db import Base, engine, init_db
from app.http import Http


@pytest.fixture
def fresh_db():
    from app import models  # noqa: F401  (register tables)
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS jobs_fts"))  # not part of the ORM metadata
    init_db()
    yield


def make_http(handler) -> Http:
    """An Http whose requests are answered by handler(request) -> httpx.Response."""
    return Http(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
