"""Database layer. SQLite by default (local), any SQLAlchemy URL via DATABASE_URL (e.g. Postgres)."""
import os
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    project: Mapped[str] = mapped_column(String(100), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)   # only the hash is stored
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("project", "name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RequestLog(Base):
    """Metadata only. Prompts and model outputs are deliberately NOT stored."""
    __tablename__ = "request_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    api_key_id: Mapped[int] = mapped_column(Integer)
    policy_name: Mapped[str] = mapped_column(String(100))
    served_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempts: Mapped[list] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean)
    fallback_used: Mapped[bool] = mapped_column(Boolean)
    simulated: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_reason: Mapped[str] = mapped_column(String(500))


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./stackpilot.db")
    return url.replace("postgres://", "postgresql://", 1) if url.startswith("postgres://") else url


@lru_cache
def get_engine():
    url = database_url()
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return engine


def get_db():
    with Session(get_engine()) as session:
        yield session
