"""add per-WorldCharacter community profile and activity repertoire

Revision ID: 20260808_0073
Revises: 20260807_0072
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260808_0073"
down_revision: str | None = "20260807_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

JSON_DOCUMENT = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "world_community_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("visible_summary", sa.String(length=280), nullable=False),
        sa.Column("core_interests", JSON_DOCUMENT, nullable=False),
        sa.Column("adjacent_interests", JSON_DOCUMENT, nullable=False),
        sa.Column("avoid_topics", JSON_DOCUMENT, nullable=False),
        sa.Column("discovery_openness", sa.Integer(), nullable=False),
        sa.Column("search_keywords", JSON_DOCUMENT, nullable=False),
        sa.Column("action_profile", JSON_DOCUMENT, nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(length=80), nullable=False),
        sa.Column("character_contract_hash", sa.String(length=64), nullable=False),
        sa.Column("world_contract_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("credential_id", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','ready','stale','superseded','failed')",
            name="ck_world_community_profiles_status",
        ),
        sa.CheckConstraint(
            "discovery_openness >= 0 AND discovery_openness <= 100",
            name="ck_world_community_profiles_openness",
        ),
        sa.CheckConstraint(
            "schema_version >= 1", name="ck_world_community_profiles_schema"
        ),
        sa.ForeignKeyConstraint(["world_character_id"], ["world_characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_world_community_profiles_character_status",
        "world_community_profiles",
        ["world_character_id", "status"],
    )
    op.create_index(
        "uq_world_community_profiles_current_ready",
        "world_community_profiles",
        ["world_character_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
        sqlite_where=sa.text("status = 'ready'"),
    )

    op.create_table(
        "world_activity_repertoires",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(length=80), nullable=False),
        sa.Column("character_contract_hash", sa.String(length=64), nullable=False),
        sa.Column("world_contract_hash", sa.String(length=64), nullable=False),
        sa.Column("community_profile_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("credential_id", sa.String(length=64), nullable=False),
        sa.Column("validation_summary", JSON_DOCUMENT, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','ready','stale','superseded','failed')",
            name="ck_world_activity_repertoires_status",
        ),
        sa.CheckConstraint(
            "schema_version >= 1", name="ck_world_activity_repertoires_schema"
        ),
        sa.ForeignKeyConstraint(
            ["community_profile_id"], ["world_community_profiles.id"]
        ),
        sa.ForeignKeyConstraint(["world_character_id"], ["world_characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_world_activity_repertoires_character_status",
        "world_activity_repertoires",
        ["world_character_id", "status"],
    )
    op.create_index(
        "uq_world_activity_repertoires_current_ready",
        "world_activity_repertoires",
        ["world_character_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
        sqlite_where=sa.text("status = 'ready'"),
    )

    op.create_table(
        "world_activity_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("repertoire_id", sa.String(length=64), nullable=False),
        sa.Column("daypart", sa.String(length=20), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("activity_kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("activity_seed", sa.String(length=500), nullable=False),
        sa.Column("place_key", sa.String(length=64), nullable=True),
        sa.Column("social_mode", sa.String(length=32), nullable=False),
        sa.Column("canonical_signature", sa.String(length=64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_world_activity_candidates_daypart",
        ),
        sa.CheckConstraint(
            "social_mode IN ('solo','open_to_interaction','cooperative')",
            name="ck_world_activity_candidates_social_mode",
        ),
        sa.CheckConstraint(
            "activity_kind IN ('duty','rest','self_care','hobby','exploration',"
            "'social','maintenance','challenge')",
            name="ck_world_activity_candidates_kind",
        ),
        sa.CheckConstraint(
            "ordinal >= 1 AND ordinal <= 10",
            name="ck_world_activity_candidates_ordinal",
        ),
        sa.ForeignKeyConstraint(
            ["repertoire_id"], ["world_activity_repertoires.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repertoire_id",
            "canonical_signature",
            name="uq_world_activity_candidates_signature",
        ),
        sa.UniqueConstraint(
            "repertoire_id",
            "daypart",
            "ordinal",
            name="uq_world_activity_candidates_ordinal",
        ),
    )
    op.create_index(
        "ix_world_activity_candidates_repertoire_daypart",
        "world_activity_candidates",
        ["repertoire_id", "daypart"],
    )

    op.create_table(
        "world_character_setup_attempts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("retry_of_attempt_id", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("credential_id", sa.String(length=64), nullable=False),
        sa.Column("consent_policy_version", sa.String(length=40), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logical_call_count", sa.Integer(), nullable=False),
        sa.Column("physical_request_count", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("failure_class", sa.String(length=80), nullable=True),
        sa.Column("safe_error_code", sa.String(length=80), nullable=True),
        sa.Column("prompt_token_count", sa.Integer(), nullable=True),
        sa.Column("output_token_count", sa.Integer(), nullable=True),
        sa.Column("total_token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('community_profile','repertoire','approval')",
            name="ck_world_character_setup_attempts_stage",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_world_character_setup_attempts_status",
        ),
        sa.CheckConstraint(
            "logical_call_count >= 0 AND physical_request_count >= 0",
            name="ck_world_character_setup_attempts_call_counts",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["retry_of_attempt_id"], ["world_character_setup_attempts.id"]
        ),
        sa.ForeignKeyConstraint(["world_character_id"], ["world_characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "world_character_id",
            "stage",
            "idempotency_key",
            name="uq_world_character_setup_attempts_request",
        ),
    )
    op.create_index(
        "ix_world_character_setup_attempts_character_status",
        "world_character_setup_attempts",
        ["world_character_id", "status"],
    )
    op.create_index(
        "ix_world_character_setup_attempts_owner_created",
        "world_character_setup_attempts",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "uq_world_character_setup_attempts_running_stage",
        "world_character_setup_attempts",
        ["world_character_id", "stage"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_world_character_setup_attempts_running_stage",
        table_name="world_character_setup_attempts",
    )
    op.drop_index(
        "ix_world_character_setup_attempts_owner_created",
        table_name="world_character_setup_attempts",
    )
    op.drop_index(
        "ix_world_character_setup_attempts_character_status",
        table_name="world_character_setup_attempts",
    )
    op.drop_table("world_character_setup_attempts")
    op.drop_index(
        "ix_world_activity_candidates_repertoire_daypart",
        table_name="world_activity_candidates",
    )
    op.drop_table("world_activity_candidates")
    op.drop_index(
        "uq_world_activity_repertoires_current_ready",
        table_name="world_activity_repertoires",
    )
    op.drop_index(
        "ix_world_activity_repertoires_character_status",
        table_name="world_activity_repertoires",
    )
    op.drop_table("world_activity_repertoires")
    op.drop_index(
        "uq_world_community_profiles_current_ready",
        table_name="world_community_profiles",
    )
    op.drop_index(
        "ix_world_community_profiles_character_status",
        table_name="world_community_profiles",
    )
    op.drop_table("world_community_profiles")
