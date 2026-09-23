"""Persistent character state and explicit activity engine policy.

These are local runtime records, not World package content. Missing policy rows
inherit the global default; they never materialize an explicit V1 override.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.world_characters.models import JSON_DOCUMENT
from app.models import Base


class CharacterActivityState(Base):
    __tablename__ = "world_character_activity_states"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"], ondelete="CASCADE"),
        CheckConstraint("version >= 1", name="ck_activity_state_version"),
        CheckConstraint("mood_intensity IS NULL OR (mood_intensity >= 0 AND mood_intensity <= 100)", name="ck_activity_state_intensity"),
        CheckConstraint("(mood IS NULL AND mood_intensity IS NULL AND state_note IS NULL) OR (mood IS NOT NULL AND mood_intensity IS NOT NULL AND state_note IS NOT NULL)", name="ck_activity_state_complete"),
        CheckConstraint("mood IS NULL OR mood IN ('neutral','curious','joyful','hopeful','calm','concerned','frustrated','sad','embarrassed')", name="ck_activity_state_mood"),
    )
    world_character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mood: Mapped[str | None] = mapped_column(String(24))
    mood_intensity: Mapped[int | None] = mapped_column(Integer)
    state_note: Mapped[str | None] = mapped_column(String(160))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str | None] = mapped_column(String(100))


class ActivityStateReceipt(Base):
    __tablename__ = "world_character_state_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"], ondelete="CASCADE"),
    )
    decision_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_keys: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    judged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActivityEnginePolicy(Base):
    __tablename__ = "activity_engine_policies"
    __table_args__ = (
        CheckConstraint("engine IN ('current','personalized_graph_v2')", name="ck_activity_engine"),
        CheckConstraint("version >= 1", name="ck_activity_engine_version"),
    )
    scope_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    world_id: Mapped[str | None] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"))
    world_character_id: Mapped[str | None] = mapped_column(ForeignKey("world_characters.id", ondelete="CASCADE"))
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActivityGraphRun(Base):
    __tablename__ = "activity_graph_runs"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"], ondelete="CASCADE"),
    )
    activity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
