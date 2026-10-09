"""Append-only parent resolution tied to the original manifest's lifetime."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MemorySituationSourceBinding(Base):
    __tablename__ = "memory_situation_source_bindings"
    __table_args__ = (CheckConstraint("entry_ordinal >= 0 AND basis_ordinal >= 0", name="ck_situation_binding_ordinals"),)
    manifest_id: Mapped[str] = mapped_column(ForeignKey("memory_situation_manifests.id", ondelete="CASCADE"), primary_key=True)
    entry_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    resolution_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    original_entry_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    basis_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    basis_source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    basis_source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_source: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution_digest: Mapped[str] = mapped_column(String(64), nullable=False)
