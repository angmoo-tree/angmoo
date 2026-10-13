"""Durable scoped World deletion, additive and forward-only."""
from alembic import op
from app.runtime.migrations.sqlite_versions.world_deletion_v37 import upgrade as apply_upgrade

revision = "20261012_0114"
down_revision = "20261010_0113"
branch_labels = depends_on = None


def upgrade():
    apply_upgrade(op.get_bind())


def downgrade():
    raise RuntimeError("forward_only_migration")
