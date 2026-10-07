"""Durable activity situations and bounded application runs."""
from alembic import op

revision = "20261008_0108"
down_revision = "20261006_0107"
branch_labels = None
depends_on = None


def upgrade():
    from app.runtime.migrations.sqlite_versions import activity_situation_v31
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        activity_situation_v31.upgrade(connection)
    else:
        from app.runtime.persistence.model_registration import register_models
        metadata = register_models()
        for table in metadata.sorted_tables:
            if table.name in activity_situation_v31.NEW_TABLES:
                table.create(connection)
        activity_situation_v31.inherit_settings(connection)


def downgrade():
    raise RuntimeError("activity_situation_migration_forward_only")
