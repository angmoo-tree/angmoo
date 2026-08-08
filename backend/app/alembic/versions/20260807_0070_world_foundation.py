"""add World Creator foundation and per-World Character boundaries

Revision ID: 20260807_0070
Revises: 20260804_0069
Create Date: 2026-08-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260807_0070"
down_revision: str | None = "20260804_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


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
        "worlds",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=96), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("tagline", sa.String(length=160), nullable=False),
        sa.Column("setting_description", sa.Text(), nullable=False),
        sa.Column("daily_life_description", sa.Text(), nullable=False),
        sa.Column(
            "genre_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "tone_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("banner_media_id", sa.String(length=500), nullable=True),
        sa.Column("banner_alt_text", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("join_policy", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(length=40), nullable=False),
        sa.Column("contract_hash", sa.String(length=64), nullable=False),
        sa.Column("readiness_status", sa.String(length=20), nullable=False),
        sa.Column("additional_generation_guidance", sa.Text(), nullable=False),
        sa.Column("create_idempotency_key", sa.String(length=128), nullable=False),
        *_timestamps(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "visibility IN ('private','unlisted','public')",
            name="ck_worlds_visibility",
        ),
        sa.CheckConstraint(
            "join_policy IN ('open','approval_required','invite_only','private')",
            name="ck_worlds_join_policy",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_worlds_status"
        ),
        sa.CheckConstraint(
            "readiness_status IN ('not_ready','publish_ready','stale')",
            name="ck_worlds_readiness_status",
        ),
        sa.CheckConstraint(
            "definition_version >= 1", name="ck_worlds_definition_version"
        ),
        sa.CheckConstraint("row_version >= 1", name="ck_worlds_row_version"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_worlds_slug"),
        sa.UniqueConstraint(
            "owner_user_id",
            "create_idempotency_key",
            name="uq_worlds_owner_create_request",
        ),
    )
    op.create_index("ix_worlds_owner_status", "worlds", ["owner_user_id", "status"])
    op.create_index(
        "ix_worlds_visibility_status", "worlds", ["visibility", "status"]
    )

    op.create_table(
        "world_memberships",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=280), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('owner','editor','member')", name="ck_world_memberships_role"
        ),
        sa.CheckConstraint(
            "status IN ('pending','active','left','rejected','banned')",
            name="ck_world_memberships_status",
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("world_id", "id", name="uq_world_memberships_world_id"),
        sa.UniqueConstraint(
            "world_id", "user_id", name="uq_world_memberships_world_user"
        ),
    )
    op.create_index(
        "ix_world_memberships_user_status",
        "world_memberships",
        ["user_id", "status"],
    )

    op.create_table(
        "world_places",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("place_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "available_dayparts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "access_role_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_places_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_world_places_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "world_id", "place_key", name="uq_world_places_world_key"
        ),
    )
    op.create_index(
        "ix_world_places_world_status", "world_places", ["world_id", "status"]
    )

    op.create_table(
        "world_roles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "responsibilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "allowed_activity_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "autonomous_allowed", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_roles_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_world_roles_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("world_id", "role_key", name="uq_world_roles_world_key"),
    )
    op.create_index(
        "ix_world_roles_world_status", "world_roles", ["world_id", "status"]
    )

    op.create_table(
        "world_daypart_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("daypart", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "available_features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "restricted_features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_world_daypart_profiles_daypart",
        ),
        sa.CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_daypart_profiles_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_world_daypart_profiles_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "world_id",
            "daypart",
            name="uq_world_daypart_profiles_world_daypart",
        ),
    )

    op.create_table(
        "world_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("rule_kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "rule_kind IN ('allow','forbid')", name="ck_world_rules_kind"
        ),
        sa.CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_rules_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_world_rules_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "world_id",
            "rule_key",
            "rule_kind",
            name="uq_world_rules_world_key_kind",
        ),
    )
    op.create_index(
        "ix_world_rules_world_status", "world_rules", ["world_id", "status"]
    )

    op.create_table(
        "world_glossary_terms",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("term_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("meaning", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('enabled','disabled','archived')",
            name="ck_world_glossary_terms_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_world_glossary_terms_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "world_id", "term_key", name="uq_world_glossary_terms_world_key"
        ),
    )
    op.create_index(
        "ix_world_glossary_terms_world_status",
        "world_glossary_terms",
        ["world_id", "status"],
    )

    op.create_table(
        "world_characters",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("membership_id", sa.String(length=64), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "autonomous_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("local_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("character_contract_hash", sa.String(length=64), nullable=True),
        sa.Column("world_contract_hash", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','inactive','active','left','rejected','banned')",
            name="ck_world_characters_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_world_characters_version"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "membership_id"],
            ["world_memberships.world_id", "world_memberships.id"],
            name="fk_world_characters_membership_world",
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "character_id", name="uq_world_characters_id_character"),
        sa.UniqueConstraint(
            "world_id", "character_id", name="uq_world_characters_world_character"
        ),
    )
    op.create_index(
        "ix_world_characters_world_status", "world_characters", ["world_id", "status"]
    )
    op.create_index(
        "ix_world_characters_character_status",
        "world_characters",
        ["character_id", "status"],
    )

    op.create_table(
        "character_active_worlds",
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_character_active_worlds_version"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(
            ["world_character_id", "character_id"],
            ["world_characters.id", "world_characters.character_id"],
            name="fk_character_active_worlds_same_character",
        ),
        sa.PrimaryKeyConstraint("character_id"),
        sa.UniqueConstraint(
            "character_id", "idempotency_key", name="uq_character_active_worlds_request"
        ),
        sa.UniqueConstraint("world_character_id", name="uq_character_active_worlds_wc"),
    )


def downgrade() -> None:
    op.drop_table("character_active_worlds")
    op.drop_index("ix_world_characters_character_status", table_name="world_characters")
    op.drop_index("ix_world_characters_world_status", table_name="world_characters")
    op.drop_table("world_characters")
    op.drop_index(
        "ix_world_glossary_terms_world_status", table_name="world_glossary_terms"
    )
    op.drop_table("world_glossary_terms")
    op.drop_index("ix_world_rules_world_status", table_name="world_rules")
    op.drop_table("world_rules")
    op.drop_table("world_daypart_profiles")
    op.drop_index("ix_world_roles_world_status", table_name="world_roles")
    op.drop_table("world_roles")
    op.drop_index("ix_world_places_world_status", table_name="world_places")
    op.drop_table("world_places")
    op.drop_index("ix_world_memberships_user_status", table_name="world_memberships")
    op.drop_table("world_memberships")
    op.drop_index("ix_worlds_visibility_status", table_name="worlds")
    op.drop_index("ix_worlds_owner_status", table_name="worlds")
    op.drop_table("worlds")
