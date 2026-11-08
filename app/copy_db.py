"""Copy the collected jobs from this app's database (DATABASE_URL, usually the local SQLite file) to
another database, e.g. a new Supabase Postgres, so a deployment starts with history and doesn't
re-announce anything.

    python -m app.copy_db --to "postgresql://USER:PASSWORD@HOST:5432/postgres" --lite
"""
import argparse
from datetime import datetime, timezone
from sqlalchemy import create_engine, func, select, text
from app.db import Base, engine as source_engine, normalize_database_url
from app.models import Job, SourceState

BATCH = 2000


def _utc(row: dict) -> dict:
    # SQLite returns naive datetimes; Postgres wants them marked as UTC.
    return {k: (v.replace(tzinfo=timezone.utc) if isinstance(v, datetime) and v.tzinfo is None else v) for k, v in row.items()}


def copy_database(target_url: str, lite: bool, replace: bool) -> dict:
    url = normalize_database_url(target_url)
    connect_args = {"prepare_threshold": None} if url.startswith("postgresql") else {}
    target = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(bind=target)
    jobs, states = Job.__table__, SourceState.__table__

    with target.begin() as dst:
        existing = dst.scalar(select(func.count()).select_from(jobs))
        if existing and not replace:
            raise SystemExit(f"The target already has {existing} jobs; pass --replace to overwrite them.")
        if existing:
            dst.execute(jobs.delete())
            dst.execute(states.delete())

    copied = 0
    with source_engine.connect() as src, target.begin() as dst:
        dst.execute(states.insert(), [_utc(dict(r._mapping)) for r in src.execute(select(states))])
        last_id = 0
        while True:
            rows = [dict(r._mapping) for r in src.execute(select(jobs).where(jobs.c.id > last_id).order_by(jobs.c.id).limit(BATCH))]
            if not rows:
                break
            for row in rows:
                if lite:
                    row["description"] = None
            dst.execute(jobs.insert(), [_utc(r) for r in rows])
            copied += len(rows)
            last_id = rows[-1]["id"]
            print(f"copied {copied} jobs")
        if target.dialect.name == "postgresql":
            # Rows were inserted with their ids, so move the id counter past them.
            dst.execute(text("SELECT setval(pg_get_serial_sequence('jobs', 'id'), (SELECT COALESCE(MAX(id), 1) FROM jobs))"))
    return {"jobs": copied}


def main():
    parser = argparse.ArgumentParser(description="Copy collected jobs to another database.")
    parser.add_argument("--to", required=True, help="target database URL, e.g. postgresql://user:pass@host:5432/postgres")
    parser.add_argument("--lite", action="store_true", help="leave out job descriptions (for small free databases)")
    parser.add_argument("--replace", action="store_true", help="overwrite jobs already in the target")
    args = parser.parse_args()
    print(copy_database(args.to, lite=args.lite, replace=args.replace))


if __name__ == "__main__":
    main()
