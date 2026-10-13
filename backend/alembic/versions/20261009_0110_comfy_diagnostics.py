"""Nullable safe ComfyUI diagnostics, forward only."""
from alembic import op
import sqlalchemy as sa

revision = "20261009_0110"
down_revision = "20261008_0109"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("post_image_generation_jobs", sa.Column("provider_diagnostic_json", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError("comfy_diagnostics_migration_forward_only")
