"""Freeze explicit Topic request context without changing historical topics."""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0103"
down_revision = "20260929_0102"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("social_recommendation_preparations", sa.Column("request_snapshot", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("topic_request_history_forward_only")
