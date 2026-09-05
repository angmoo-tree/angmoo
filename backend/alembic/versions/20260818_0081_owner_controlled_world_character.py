"""add owner-controlled WorldCharacter identity foundation

Revision ID: 20260818_0081
Revises: 20260816_0080
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260818_0081"
down_revision: str | None = "20260816_0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "world_characters",
        sa.Column(
            "control_mode",
            sa.String(length=24),
            nullable=True,
            server_default="autonomous",
        ),
    )
    op.add_column(
        "world_characters",
        sa.Column(
            "owner_user_id",
            sa.String(length=64),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE world_characters "
            "SET control_mode = 'autonomous', owner_user_id = NULL "
            "WHERE control_mode IS NULL"
        )
    )
    op.alter_column(
        "world_characters",
        "control_mode",
        existing_type=sa.String(length=24),
        nullable=False,
        server_default="autonomous",
    )
    op.create_check_constraint(
        "ck_world_characters_control_mode",
        "world_characters",
        "control_mode IN ('autonomous','owner_controlled')",
    )
    op.create_check_constraint(
        "ck_world_characters_owner_binding",
        "world_characters",
        "(control_mode = 'autonomous' AND owner_user_id IS NULL) OR "
        "(control_mode = 'owner_controlled' AND owner_user_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_world_characters_owner_autonomy_disabled",
        "world_characters",
        "control_mode <> 'owner_controlled' OR autonomous_enabled = false",
    )
    op.create_index(
        "ix_world_characters_owner_status",
        "world_characters",
        ["owner_user_id", "status"],
    )
    op.create_index(
        "uq_world_characters_active_owner_controlled",
        "world_characters",
        ["world_id", "owner_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "control_mode = 'owner_controlled' AND status = 'active'"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    owner_controlled_count = bind.scalar(
        sa.text(
            "SELECT count(*) FROM world_characters "
            "WHERE control_mode = 'owner_controlled'"
        )
    )
    if int(owner_controlled_count or 0) > 0:
        raise RuntimeError(
            "downgrade_refused_owner_controlled_world_characters_exist: "
            "back up or remove owner-controlled identities explicitly before "
            "downgrading to 20260816_0080"
        )
    op.drop_index(
        "uq_world_characters_active_owner_controlled",
        table_name="world_characters",
    )
    op.drop_index("ix_world_characters_owner_status", table_name="world_characters")
    op.drop_constraint(
        "ck_world_characters_owner_autonomy_disabled",
        "world_characters",
        type_="check",
    )
    op.drop_constraint(
        "ck_world_characters_owner_binding",
        "world_characters",
        type_="check",
    )
    op.drop_constraint(
        "ck_world_characters_control_mode",
        "world_characters",
        type_="check",
    )
    op.drop_column("world_characters", "owner_user_id")
    op.drop_column("world_characters", "control_mode")
