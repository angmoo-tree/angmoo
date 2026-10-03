"""Local UI preference and authenticated installation environment."""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0105"
down_revision = "20260930_0104"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        from app.runtime.migrations.sqlite_versions.environment_v27 import upgrade as sqlite_upgrade
        sqlite_upgrade(connection)
        return
    from app.domains.identity.models_environment import EnvironmentTimezoneChange, LocalEnvironment
    op.add_column("users", sa.Column("ui_language", sa.String(2), nullable=True))
    op.add_column("users", sa.Column("ui_preference_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agent_slots", sa.Column("timezone_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("local_bot_action_quota_buckets", sa.Column("period_state", sa.JSON(), nullable=True))
    op.add_column("memory_maintenance_jobs", sa.Column("environment_snapshot", sa.JSON(), nullable=True))
    LocalEnvironment.__table__.create(connection)
    EnvironmentTimezoneChange.__table__.create(connection)


def downgrade():
    raise RuntimeError("local_environment_forward_only")
