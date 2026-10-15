"""Add deterministic World notification delivery identities, preserving history."""
from alembic import op
from app.runtime.migrations.sqlite_versions.world_notifications_v38 import upgrade as apply_upgrade

revision = "20261015_0115"
down_revision = "20261012_0114"
branch_labels = depends_on = None


def upgrade():
    apply_upgrade(op.get_bind())


def downgrade():
    raise RuntimeError("forward_only_migration")
