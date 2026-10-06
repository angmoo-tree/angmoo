"""Subject profiles, explicit full preparation and canonical private constraints."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class MemorySubjectProfile(Base):
    __tablename__ = "memory_subject_profiles"
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id"), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    thinking_level: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryIndexPreparation(Base):
    __tablename__ = "memory_index_preparations"
    __table_args__ = (CheckConstraint("state IN ('needs_preparation','running','ready','error')", name="ck_memory_index_preparation_state"),)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[str] = mapped_column(String(128), nullable=False)
    source_generation: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_revision: Mapped[int | None] = mapped_column(Integer)
    request_key: Mapped[str | None] = mapped_column(String(128))
    cursor: Mapped[str | None] = mapped_column(String(64))
    last_code: Mapped[str | None] = mapped_column(String(80))


class MemoryEpisodeRestriction(Base):
    __tablename__ = "memory_episode_restrictions"
    __table_args__ = (CheckConstraint("mode IN ('public','private_thread')", name="ck_memory_episode_restriction_mode"),)
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(64))
    # Identities/digests only. Missing source/thread rows cannot promote access.
    sources_json: Mapped[str] = mapped_column(Text, nullable=False)
    priors_json: Mapped[str] = mapped_column(Text, nullable=False)
