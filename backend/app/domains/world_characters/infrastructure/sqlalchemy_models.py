"""SQLAlchemy persistence owned by the WorldCharacter domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class WorldCharacter(Base):
    __tablename__ = "world_characters"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','inactive','active','left','rejected','banned')",
            name="ck_world_characters_status",
        ),
        CheckConstraint(
            "control_mode IN ('autonomous','owner_controlled')",
            name="ck_world_characters_control_mode",
        ),
        CheckConstraint(
            "(control_mode = 'autonomous' AND owner_user_id IS NULL) OR "
            "(control_mode = 'owner_controlled' AND owner_user_id IS NOT NULL)",
            name="ck_world_characters_owner_binding",
        ),
        CheckConstraint(
            "control_mode <> 'owner_controlled' OR autonomous_enabled = false",
            name="ck_world_characters_owner_autonomy_disabled",
        ),
        CheckConstraint(
            "activity_runtime_mode IN ('legacy_resident_v1','routine_resident_v1')",
            name="ck_world_characters_activity_runtime_mode",
        ),
        CheckConstraint(
            "feed_runtime_mode IN ('legacy_latest_v1','keyword_search_v1')",
            name="ck_world_characters_feed_runtime_mode",
        ),
        CheckConstraint("version >= 1", name="ck_world_characters_version"),
        ForeignKeyConstraint(
            ["world_id", "membership_id"],
            ["world_memberships.world_id", "world_memberships.id"],
            name="fk_world_characters_membership_world",
        ),
        UniqueConstraint(
            "world_id", "character_id", name="uq_world_characters_world_character"
        ),
        UniqueConstraint("id", "world_id", name="uq_world_characters_id_world"),
        UniqueConstraint("id", "character_id", name="uq_world_characters_id_character"),
        Index("ix_world_characters_world_status", "world_id", "status"),
        Index("ix_world_characters_character_status", "character_id", "status"),
        Index("ix_world_characters_owner_status", "owner_user_id", "status"),
        Index(
            "uq_world_characters_active_owner_controlled",
            "world_id",
            "owner_user_id",
            unique=True,
            postgresql_where=text(
                "control_mode = 'owner_controlled' AND status = 'active'"
            ),
            sqlite_where=text(
                "control_mode = 'owner_controlled' AND status = 'active'"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    control_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, default="autonomous", server_default="autonomous"
    )
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    autonomous_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    activity_runtime_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="legacy_resident_v1",
        server_default="legacy_resident_v1",
    )
    feed_runtime_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="legacy_latest_v1",
        server_default="legacy_latest_v1",
    )
    local_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    character_contract_hash: Mapped[str | None] = mapped_column(String(64))
    world_contract_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CharacterActiveWorld(Base):
    __tablename__ = "character_active_worlds"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_character_active_worlds_version"),
        ForeignKeyConstraint(
            ["world_character_id", "character_id"],
            ["world_characters.id", "world_characters.character_id"],
            name="fk_character_active_worlds_same_character",
        ),
        UniqueConstraint(
            "character_id", "idempotency_key", name="uq_character_active_worlds_request"
        ),
    )

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["CharacterActiveWorld", "WorldCharacter"]
