"""Preserve explicit local session termination with client generations."""
from alembic import op
from app.runtime.migrations.sqlite_versions.local_client_v40 import upgrade as apply_upgrade

revision = "20261019_0117"
down_revision = "20261016_0116"
branch_labels = depends_on = None


def upgrade():
    apply_upgrade(op.get_bind())


def downgrade():
    raise RuntimeError("forward_only_migration")
