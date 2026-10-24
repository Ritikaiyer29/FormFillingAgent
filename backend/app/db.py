from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, create_engine, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

_JSON = JSON().with_variant(JSONB(), "postgresql")
connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(32))
    variant: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # draft -> collecting -> ready_for_submission -> submitted (call lifecycle is tracked separately)
    state: Mapped[str] = mapped_column(String(32), default="draft")
    call_status: Mapped[str] = mapped_column(String(32), default="not_started")
    delivery_status: Mapped[str] = mapped_column(String(32), default="not_submitted")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(_JSON, default=dict)
    phone: Mapped[str] = mapped_column(String(20))
    call_language: Mapped[str] = mapped_column(String(32))
    language_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    otp_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    help_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    capability_nonce: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AppEvent(Base):
    """Durable change history and outbox. Payloads never hold restricted values."""
    __tablename__ = "app_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(_JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Operation(Base):
    """Claimed operation ids, so a repeated tool call returns the first result without new side effects."""
    __tablename__ = "operations"
    op_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    response: Mapped[dict] = mapped_column(_JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def init_db():
    Base.metadata.create_all(engine)
