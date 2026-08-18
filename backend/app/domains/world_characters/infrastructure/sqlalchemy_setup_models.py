from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domains.world_characters.infrastructure.sqlalchemy_models import JSON_DOCUMENT


_CURRENT_READY = text("status = 'ready'")


class WorldCommunityProfile(Base):
    __tablename__ = "world_community_profiles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','ready','stale','superseded','failed')",
            name="ck_world_community_profiles_status",
        ),
        CheckConstraint(
            "discovery_openness >= 0 AND discovery_openness <= 100",
            name="ck_world_community_profiles_openness",
        ),
        CheckConstraint("schema_version >= 1", name="ck_world_community_profiles_schema"),
        Index(
            "uq_world_community_profiles_current_ready",
            "world_character_id",
            unique=True,
            postgresql_where=_CURRENT_READY,
            sqlite_where=_CURRENT_READY,
        ),
        Index(
            "ix_world_community_profiles_character_status",
            "world_character_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_character_id: Mapped[str] = mapped_column(
        ForeignKey("world_characters.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    visible_summary: Mapped[str] = mapped_column(String(280), nullable=False)
    core_interests: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    adjacent_interests: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    avoid_topics: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    discovery_openness: Mapped[int] = mapped_column(Integer, nullable=False)
    search_keywords: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    action_profile: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    character_contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    world_contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_id: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorldActivityRepertoire(Base):
    __tablename__ = "world_activity_repertoires"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','ready','stale','superseded','failed')",
            name="ck_world_activity_repertoires_status",
        ),
        CheckConstraint("schema_version >= 1", name="ck_world_activity_repertoires_schema"),
        Index(
            "uq_world_activity_repertoires_current_ready",
            "world_character_id",
            unique=True,
            postgresql_where=_CURRENT_READY,
            sqlite_where=_CURRENT_READY,
        ),
        Index(
            "ix_world_activity_repertoires_character_status",
            "world_character_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_character_id: Mapped[str] = mapped_column(
        ForeignKey("world_characters.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    character_contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    world_contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    community_profile_id: Mapped[str] = mapped_column(
        ForeignKey("world_community_profiles.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_id: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorldActivityCandidate(Base):
    __tablename__ = "world_activity_candidates"
    __table_args__ = (
        CheckConstraint(
            "daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_world_activity_candidates_daypart",
        ),
        CheckConstraint(
            "social_mode IN ('solo','open_to_interaction','cooperative')",
            name="ck_world_activity_candidates_social_mode",
        ),
        CheckConstraint(
            "activity_kind IN ('duty','rest','self_care','hobby','exploration',"
            "'social','maintenance','challenge')",
            name="ck_world_activity_candidates_kind",
        ),
        CheckConstraint(
            "ordinal >= 1 AND ordinal <= 10",
            name="ck_world_activity_candidates_ordinal",
        ),
        UniqueConstraint(
            "repertoire_id",
            "canonical_signature",
            name="uq_world_activity_candidates_signature",
        ),
        UniqueConstraint(
            "repertoire_id",
            "daypart",
            "ordinal",
            name="uq_world_activity_candidates_ordinal",
        ),
        Index(
            "ix_world_activity_candidates_repertoire_daypart",
            "repertoire_id",
            "daypart",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repertoire_id: Mapped[str] = mapped_column(
        ForeignKey("world_activity_repertoires.id"), nullable=False
    )
    daypart: Mapped[str] = mapped_column(String(20), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_seed: Mapped[str] = mapped_column(String(500), nullable=False)
    place_key: Mapped[str | None] = mapped_column(String(64))
    social_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorldCharacterSetupAttempt(Base):
    __tablename__ = "world_character_setup_attempts"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('community_profile','repertoire','approval')",
            name="ck_world_character_setup_attempts_stage",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_world_character_setup_attempts_status",
        ),
        CheckConstraint(
            "logical_call_count >= 0 AND physical_request_count >= 0",
            name="ck_world_character_setup_attempts_call_counts",
        ),
        UniqueConstraint(
            "owner_user_id",
            "world_character_id",
            "stage",
            "idempotency_key",
            name="uq_world_character_setup_attempts_request",
        ),
        Index(
            "ix_world_character_setup_attempts_character_status",
            "world_character_id",
            "status",
        ),
        Index(
            "ix_world_character_setup_attempts_owner_created",
            "owner_user_id",
            "created_at",
        ),
        Index(
            "uq_world_character_setup_attempts_running_stage",
            "world_character_id",
            "stage",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_character_id: Mapped[str] = mapped_column(
        ForeignKey("world_characters.id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    retry_of_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("world_character_setup_attempts.id")
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_id: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    logical_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    physical_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    failure_class: Mapped[str | None] = mapped_column(String(80))
    safe_error_code: Mapped[str | None] = mapped_column(String(80))
    prompt_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    total_token_count: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
