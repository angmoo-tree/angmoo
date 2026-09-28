"""Preserve each beat's independent state contract without rewriting snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0102"
down_revision = "20260928_0101"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activity_beats", sa.Column("state_schema_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    raise RuntimeError("routine_state_history_forward_only")
