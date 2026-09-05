"""enforce one resident slot assignment per character

Revision ID: 20260802_0067
Revises: 20260726_0066
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260802_0067"
down_revision: str | None = "20260726_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT assigned_character_id
            FROM agent_slots
            WHERE assigned_character_id IS NOT NULL
            GROUP BY assigned_character_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "duplicate resident character assignments must be resolved before 0067"
        )
    op.create_index(
        "uq_agent_slots_assigned_character_not_null",
        "agent_slots",
        ["assigned_character_id"],
        unique=True,
        postgresql_where=sa.text("assigned_character_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_agent_slots_assigned_character_not_null",
        table_name="agent_slots",
    )
