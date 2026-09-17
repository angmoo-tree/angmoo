"""Canonical embedding consent/configuration and durable eligibility, never vectors."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

MEMORY_EMBEDDING_TABLES = ("memory_embedding_settings", "memory_vector_eligibility")


class MemoryEmbeddingSetting(Base):
    __tablename__ = "memory_embedding_settings"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_memory_embedding_version"),)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_id: Mapped[str | None] = mapped_column(ForeignKey("llm_credentials.id", ondelete="SET NULL"))
    profile: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MemoryVectorEligibility(Base):
    __tablename__ = "memory_vector_eligibility"
    __table_args__ = (CheckConstraint("item_version >= 1", name="ck_memory_vector_eligibility_version"),)
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    item_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    registration_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
