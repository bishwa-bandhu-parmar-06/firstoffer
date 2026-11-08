from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

def normalize_database_url(url: str) -> str:
    """Accept the plain postgres:// URLs that Supabase and Render show, and use the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = normalize_database_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")
if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30}, pool_pre_ping=True)
else:
    # prepare_threshold=None: server-side prepared statements break behind connection poolers such as
    # Supabase's (PgBouncer in transaction mode). A small pool stays within free-tier connection limits.
    engine = create_engine(DATABASE_URL, connect_args={"prepare_threshold": None}, pool_pre_ping=True,
                           pool_size=5, max_overflow=5, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

# SQLite full-text index over the fields people search by, kept in sync with `jobs` by triggers.
FTS_COLUMNS = ("title", "company", "location", "department", "category")
_FTS_STATEMENTS = [
    f"CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5({', '.join(FTS_COLUMNS)}, "
    "content='jobs', content_rowid='id', tokenize='unicode61 remove_diacritics 2')",
    f"CREATE TRIGGER IF NOT EXISTS jobs_fts_insert AFTER INSERT ON jobs BEGIN "
    f"INSERT INTO jobs_fts(rowid, {', '.join(FTS_COLUMNS)}) VALUES (new.id, {', '.join('new.' + c for c in FTS_COLUMNS)}); END",
    f"CREATE TRIGGER IF NOT EXISTS jobs_fts_delete AFTER DELETE ON jobs BEGIN "
    f"INSERT INTO jobs_fts(jobs_fts, rowid, {', '.join(FTS_COLUMNS)}) VALUES ('delete', old.id, {', '.join('old.' + c for c in FTS_COLUMNS)}); END",
    f"CREATE TRIGGER IF NOT EXISTS jobs_fts_update AFTER UPDATE OF {', '.join(FTS_COLUMNS)} ON jobs BEGIN "
    f"INSERT INTO jobs_fts(jobs_fts, rowid, {', '.join(FTS_COLUMNS)}) VALUES ('delete', old.id, {', '.join('old.' + c for c in FTS_COLUMNS)}); "
    f"INSERT INTO jobs_fts(rowid, {', '.join(FTS_COLUMNS)}) VALUES (new.id, {', '.join('new.' + c for c in FTS_COLUMNS)}); END",
]


def _add_missing_columns():
    """Lightweight stand-in for migrations: add new nullable columns to existing tables."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing and column.nullable:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" '
                                      f'{column.type.compile(dialect=engine.dialect)}'))
            for index in table.indexes:
                index.create(conn, checkfirst=True)


def _ensure_fts():
    with engine.begin() as conn:
        # Without table statistics SQLite's planner picks poor indexes (e.g. "active" over "dedup_key").
        if not conn.execute(text("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_stat1'")).first():
            conn.execute(text("ANALYZE"))
        exists = conn.execute(text("SELECT 1 FROM sqlite_master WHERE name = 'jobs_fts'")).first()
        for statement in _FTS_STATEMENTS:
            conn.execute(text(statement))
        if not exists:
            conn.execute(text("INSERT INTO jobs_fts(jobs_fts) VALUES ('rebuild')"))


def init_db():
    from app import models  # register models
    _add_missing_columns()
    Base.metadata.create_all(bind=engine)
    if IS_SQLITE:
        _ensure_fts()
