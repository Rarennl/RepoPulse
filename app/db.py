"""Postgres in production; SQLite is supported only for local unit tests."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, Text, JSON, Float, Integer, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL

def now():
    return datetime.now(timezone.utc).timestamp()

def uid():
    return str(uuid4())

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256))
    token: Mapped[str | None] = mapped_column(Text, nullable=True)

class Repo(Base):
    __tablename__ = 'repositories'
    # Separate per-user snapshots: personal data is never reused in public reports.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(256))
    scope: Mapped[str] = mapped_column(String(128), default='public')
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    latest_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_attempt: Mapped[float] = mapped_column(Float, default=0)
    __table_args__ = (Index('uq_repo_scope', 'slug', 'scope', unique=True),)

class Analysis(Base):
    __tablename__ = 'analyses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage: Mapped[float] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON)

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(16), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=now)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(256), nullable=True)

def migrate():
    """Versioned initial schema. Later changes must be explicit migrations."""
    from sqlalchemy import text
    with engine.begin() as conn:
        if engine.dialect.name == 'postgresql':
            conn.execute(text('SELECT pg_advisory_xact_lock(724813)'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)'))
        version = conn.execute(text('SELECT max(version) FROM schema_version')).scalar()
        if version is None:
            Base.metadata.create_all(conn)
            conn.execute(text('INSERT INTO schema_version VALUES (1)'))
        elif version != 1:
            raise RuntimeError('Unsupported database schema')
