"""Durable vector work and same-transaction source revisions."""
from alembic import op
from app.runtime.migrations.sqlite_versions.vector_work_v39 import upgrade as apply_upgrade

revision = "20261016_0116"
down_revision = "20261015_0115"
branch_labels = depends_on = None


def upgrade():
    apply_upgrade(op.get_bind())


def downgrade():
    raise RuntimeError("forward_only_migration")
