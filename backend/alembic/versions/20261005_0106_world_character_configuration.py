"""Permanent import origins and World-local effective configuration."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0106"
down_revision = "20261003_0105"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    from app.runtime.migrations.sqlite_versions.world_configuration_v28 import upgrade as sqlite_upgrade, backfill
    if connection.dialect.name == "sqlite":
        sqlite_upgrade(connection)
        return
    from app.domains.characters.models_import import CharacterImportSnapshot, CharacterImportOrigin, CharacterDraftImportOrigin
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    op.add_column("agent_slots", sa.Column("admission_metadata", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("input_snapshot", sa.JSON(), nullable=True))
    for model in (CharacterImportSnapshot, CharacterImportOrigin, CharacterDraftImportOrigin, WorldCharacterConfiguration):
        model.__table__.create(connection)
    backfill(connection)


def downgrade():
    raise RuntimeError("world_character_configuration_forward_only")
