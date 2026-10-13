"""World actor image policy and independent daily attempt ledgers."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class WorldImagePolicy(Base):
    __tablename__ = "world_image_policies"
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_world_image_policy_revision"),)
    world_character_id: Mapped[str] = mapped_column(ForeignKey("world_characters.id"), primary_key=True)
    generation_limit: Mapped[int | None] = mapped_column(Integer)
    vision_limit: Mapped[int | None] = mapped_column(Integer)
    generation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=false())
    vision_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=false())
    generation_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance: Mapped[str] = mapped_column(String(80), nullable=False)


class WorldImageAttempt(Base):
    __tablename__ = "world_image_attempts"
    __table_args__ = (
        UniqueConstraint("world_character_id", "purpose", "request_key", name="uq_world_image_attempt_request"),
        CheckConstraint("purpose IN ('image','vision')", name="ck_world_image_attempt_purpose"),
        CheckConstraint("state IN ('reserved','submitted','completed','failed','unknown','released')", name="ck_world_image_attempt_state"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_character_id: Mapped[str] = mapped_column(ForeignKey("world_characters.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(12), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    period_date: Mapped[str] = mapped_column(String(10), nullable=False)
    lane: Mapped[str] = mapped_column(String(12), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
