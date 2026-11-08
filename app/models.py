from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

def utcnow():
    return datetime.now(timezone.utc)

def as_utc(value: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes even for timezone-aware columns.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    # Identifies the configured source (e.g. "workday:nvidia.wd5.myworkdayjobs.com:nvidia:NVIDIAExternalCareerSite").
    source_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    source_job_id: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workplace_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(String(250), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Complete polls in a row that did not include this job; reset whenever it is seen again.
    missed_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Derived by app.enrich from the fields above; recomputed when they change or the rules change.
    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # Every country the job is offered in, as "|India|United States|" so a LIKE '%|India|%' filter works.
    countries: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Same company + normalized title + place: used to show re-posts of one opening as a single result.
    dedup_key: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    enrich_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Date used for "newest first": the posting date, or when we first saw it unless that was the
    # source's first (seed) poll, where "first seen" just means "already open when we started".
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by app.enrich.refresh_groups(): one primary posting per dedup group, and the group's size.
    is_primary: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    similar_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        UniqueConstraint("source_key", "source_job_id", name="uq_source_job"),
        Index("ix_jobs_active_first_seen", "active", "first_seen_at"),
        Index("ix_jobs_primary_listed", "active", "is_primary", "listed_at"),
    )

class SourceState(Base):
    __tablename__ = "source_state"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    company: Mapped[str] = mapped_column(String(250), nullable=False)
    # Set after the first successful poll; jobs found on that seed run are never announced.
    seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_job_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    company: Mapped[str] = mapped_column(String(250), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    closed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="running", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
