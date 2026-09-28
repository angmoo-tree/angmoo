"""Durable, date-scoped preparation requests and their application receipts."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.domains.routines.models.plans import JSON_DOCUMENT


class ActivityPreparationJob(Base):
    __tablename__ = "activity_preparation_jobs"
    __table_args__ = (
        UniqueConstraint("world_character_id", "local_date", "request_id", name="uq_activity_preparation_request"),
        ForeignKeyConstraint(["world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"], name="fk_activity_preparation_scope"),
        CheckConstraint("mode IN ('initial','daily','manual_plan')", name="ck_activity_preparation_mode"),
        CheckConstraint("state IN ('pending','running','waiting','ready','failed','needs_user_action','cancelled')", name="ck_activity_preparation_state"),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= 4", name="ck_activity_preparation_attempts"),
        Index("ix_activity_preparation_due", "state", "next_retry_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(40), nullable=False, default="daily-plan-v1")
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    claim_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    json_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reason_code: Mapped[str | None] = mapped_column(String(100))
    plan_id: Mapped[str | None] = mapped_column(String(64))
    plan_version: Mapped[int | None] = mapped_column(Integer)
    input_snapshot: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    applied_snapshot: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    usage_snapshot: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
