"""Permanent import origins; drafts and mutable Character rows are not origins."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, event, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base
from app.core.ids import uuid7_string


class CharacterImportSnapshot(Base):
    __tablename__ = "character_import_snapshots"
    __table_args__ = (
        CheckConstraint("kind IN ('creation','restored_initial','legacy_transition')", name="ck_character_import_snapshot_kind"),
        CheckConstraint("contract_version = 1", name="ck_character_import_snapshot_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid7_string)
    source_character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    provenance: Mapped[str] = mapped_column(String(240), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CharacterImportOrigin(Base):
    __tablename__ = "character_import_origins"
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("character_import_snapshots.id"), nullable=False, index=True)


class CharacterDraftImportOrigin(Base):
    __tablename__ = "character_draft_import_origins"
    draft_id: Mapped[str] = mapped_column(ForeignKey("agent_creation_drafts.id", ondelete="CASCADE"), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("character_import_snapshots.id"), nullable=False)


@event.listens_for(CharacterImportSnapshot, "before_update")
@event.listens_for(CharacterImportSnapshot, "before_delete")
def _immutable_snapshot(*_):
    raise ValueError("character_import_snapshot_immutable")
