"""Independent optional character background.

Revision ID: 20260927_0100
Revises: 20260927_0099
"""

from alembic import op
import sqlalchemy as sa

revision = "20260927_0100"
down_revision = "20260927_0099"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("characters", "agent_creation_drafts"):
        op.add_column(table, sa.Column("character_background", sa.Text(), nullable=False, server_default=""))


def downgrade():
    raise RuntimeError("character_background_preserves_user_settings_forward_only")
