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
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class World(Base):
    __tablename__ = "worlds"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private','unlisted','public')",
            name="ck_worlds_visibility",
        ),
        CheckConstraint(
            "join_policy IN ('open','approval_required','invite_only','private')",
            name="ck_worlds_join_policy",
        ),
        CheckConstraint(
            "status IN ('draft','published','archived')",
            name="ck_worlds_status",
        ),
        CheckConstraint(
            "readiness_status IN ('not_ready','publish_ready','stale')",
            name="ck_worlds_readiness_status",
        ),
        CheckConstraint("definition_version >= 1", name="ck_worlds_definition_version"),
        CheckConstraint("row_version >= 1", name="ck_worlds_row_version"),
        UniqueConstraint(
            "owner_user_id",
            "create_idempotency_key",
            name="uq_worlds_owner_create_request",
        ),
        Index("ix_worlds_owner_status", "owner_user_id", "status"),
        Index("ix_worlds_visibility_status", "visibility", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tagline: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    setting_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    daily_life_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    genre_tags: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    tone_tags: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    banner_media_id: Mapped[str | None] = mapped_column(String(500))
    banner_alt_text: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Seoul"
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="ko")
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="private"
    )
    join_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, default="approval_required"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    readiness_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_ready"
    )
    additional_generation_guidance: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    create_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorldMembership(Base):
    __tablename__ = "world_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner','editor','member')",
            name="ck_world_memberships_role",
        ),
        CheckConstraint(
            "status IN ('pending','active','left','rejected','banned')",
            name="ck_world_memberships_status",
        ),
        UniqueConstraint("world_id", "user_id", name="uq_world_memberships_world_user"),
        UniqueConstraint("world_id", "id", name="uq_world_memberships_world_id"),
        Index("ix_world_memberships_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(280))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorldPlace(Base):
    __tablename__ = "world_places"
    __table_args__ = (
        CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_places_status",
        ),
        CheckConstraint("version >= 1", name="ck_world_places_version"),
        UniqueConstraint("world_id", "place_key", name="uq_world_places_world_key"),
        Index("ix_world_places_world_status", "world_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    place_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    available_dayparts: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    access_role_keys: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorldRole(Base):
    __tablename__ = "world_roles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_roles_status",
        ),
        CheckConstraint("version >= 1", name="ck_world_roles_version"),
        UniqueConstraint("world_id", "role_key", name="uq_world_roles_world_key"),
        Index("ix_world_roles_world_status", "world_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    role_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    responsibilities: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    allowed_activity_scope: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    autonomous_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorldDaypartProfile(Base):
    __tablename__ = "world_daypart_profiles"
    __table_args__ = (
        CheckConstraint(
            "daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_world_daypart_profiles_daypart",
        ),
        CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_daypart_profiles_status",
        ),
        CheckConstraint("version >= 1", name="ck_world_daypart_profiles_version"),
        UniqueConstraint(
            "world_id", "daypart", name="uq_world_daypart_profiles_world_daypart"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    daypart: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    available_features: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    restricted_features: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorldRule(Base):
    __tablename__ = "world_rules"
    __table_args__ = (
        CheckConstraint("rule_kind IN ('allow','forbid')", name="ck_world_rules_kind"),
        CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_rules_status",
        ),
        CheckConstraint("version >= 1", name="ck_world_rules_version"),
        UniqueConstraint(
            "world_id", "rule_key", "rule_kind", name="uq_world_rules_world_key_kind"
        ),
        Index("ix_world_rules_world_status", "world_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorldGlossaryTerm(Base):
    __tablename__ = "world_glossary_terms"
    __table_args__ = (
        CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_glossary_terms_status",
        ),
        CheckConstraint("version >= 1", name="ck_world_glossary_terms_version"),
        UniqueConstraint(
            "world_id", "term_key", name="uq_world_glossary_terms_world_key"
        ),
        Index("ix_world_glossary_terms_world_status", "world_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    term_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    term: Mapped[str] = mapped_column(String(120), nullable=False)
    meaning: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorldCharacter(Base):
    __tablename__ = "world_characters"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','inactive','active','left','rejected','banned')",
            name="ck_world_characters_status",
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
        UniqueConstraint(
            "id", "world_id", name="uq_world_characters_id_world"
        ),
        UniqueConstraint("id", "character_id", name="uq_world_characters_id_character"),
        Index("ix_world_characters_world_status", "world_id", "status"),
        Index("ix_world_characters_character_status", "character_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    autonomous_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
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
