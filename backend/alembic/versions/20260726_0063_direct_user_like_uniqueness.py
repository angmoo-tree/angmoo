"""enforce direct user like uniqueness

Revision ID: 20260726_0063
Revises: 20260726_0062
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260726_0063"
down_revision: str | None = "20260726_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM post_likes AS duplicate
        USING post_likes AS keeper
        WHERE duplicate.character_id IS NULL
          AND keeper.character_id IS NULL
          AND duplicate.post_id = keeper.post_id
          AND duplicate.user_id = keeper.user_id
          AND duplicate.id > keeper.id
        """
    )
    op.create_index(
        "uq_post_likes_post_user_direct",
        "post_likes",
        ["post_id", "user_id"],
        unique=True,
        postgresql_where="character_id IS NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_post_likes_post_user_direct",
        table_name="post_likes",
    )
