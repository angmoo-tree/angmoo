"""Owned image assets and shared interpretation persistence."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (CheckConstraint("byte_size > 0 AND width > 0 AND height > 0", name="ck_media_asset_size"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterpretationSetting(Base):
    __tablename__ = "image_interpretation_settings"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="gemini-3.1-flash-lite", server_default="gemini-3.1-flash-lite")
    thinking_level: Mapped[str] = mapped_column(String(8), nullable=False, default="medium", server_default="medium")
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class ImageInterpretation(Base):
    __tablename__ = "image_interpretations"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_image_interpretation_cache"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("media_assets.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    thinking_level: Mapped[str] = mapped_column(String(8), nullable=False)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued")
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    recall_hint: Mapped[str | None] = mapped_column(String(120))
    result_json: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InterpretationAttempt(Base):
    __tablename__ = "image_interpretation_attempts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interpretation_id: Mapped[str] = mapped_column(ForeignKey("image_interpretations.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    quota_day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    usage_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
