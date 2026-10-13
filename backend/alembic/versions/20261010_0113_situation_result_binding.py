"""Forward empty storage for authenticated SNS normalization proofs."""
from alembic import op
from app.runtime.migrations.sqlite_versions.situation_result_binding_v36 import upgrade as apply_upgrade

revision = "20261010_0113"
down_revision = "20261010_0112"
branch_labels = None
depends_on = None


def upgrade():
    apply_upgrade(op.get_bind())


def downgrade():
    raise RuntimeError("forward_only_migration")
