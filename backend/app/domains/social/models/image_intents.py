"""Social-owned immutable intent, physical attempts and installation cap."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class ImageIntent(Base):
    __tablename__ = "post_image_intents"
    __table_args__ = (UniqueConstraint("post_id", "source_revision", "settings_revision", name="uq_post_image_intent_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    settings_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    scene: Mapped[str] = mapped_column(Text, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    credential_id: Mapped[str | None] = mapped_column(ForeignKey("media_credentials.id"))
    credential_revision: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ImageGenerationAttempt(Base):
    __tablename__ = "post_image_generation_attempts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("post_image_generation_jobs.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    quota_day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    receipt: Mapped[str | None] = mapped_column(String(160))
    usage_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ImageGenerationPolicy(Base):
    __tablename__ = "image_generation_policy"
    __table_args__ = (CheckConstraint("id = 1 AND (daily_limit IS NULL OR daily_limit > 0)", name="ck_image_policy_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
