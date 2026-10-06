"""Typed World configuration documents, independent of mutable source settings."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class WorldCharacterConfiguration(Base):
    __tablename__ = "world_character_configurations"
    world_character_id: Mapped[str] = mapped_column(ForeignKey("world_characters.id"), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("character_import_snapshots.id"), nullable=False, index=True)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
