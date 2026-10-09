"""Append-only SNS parent delivery resolution, forward only."""
from alembic import op
from app.runtime.migrations.sqlite_versions.situation_source_binding_v35 import upgrade as migrate

revision = "20261010_0112"
down_revision = "20261009_0111"
branch_labels = None
depends_on = None


def upgrade():
    migrate(op.get_bind())


def downgrade():
    raise RuntimeError("situation_source_binding_forward_only")
