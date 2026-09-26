"""Local default SNS, keyless drafts, card sources and atomic registration.

Revision ID: 20260927_0099
Revises: 20260924_0098
"""
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa

from app.runtime.migrations.sqlite_versions import creator_v21 as frozen

revision = "20260927_0099"
down_revision = "20260924_0098"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        frozen.upgrade(connection)
        return
    op.add_column("worlds", sa.Column("icon_media_id", sa.String(500)))
    op.alter_column("agent_creation_drafts", "encrypted_api_key", nullable=True)
    for name, kind, default, nullable in (
        ("contract_version", sa.Integer(), "1", False), ("revision", sa.Integer(), "1", False),
        ("target_world_id", sa.String(64), None, True), ("source_kind", sa.String(16), "direct", False),
        ("status", sa.String(16), "editing", False),
    ):
        op.add_column("agent_creation_drafts", sa.Column(name, kind, nullable=nullable, server_default=default))
    op.create_foreign_key("fk_creation_draft_target_world", "agent_creation_drafts", "worlds", ["target_world_id"], ["id"])
    # Frozen SQL uses standard SQL types except SQLite BLOB/DATETIME spellings.
    definitions = json.loads(Path(frozen.__file__).with_name("creator_v21_ddl.json").read_text(encoding="utf-8"))
    for table in frozen.NEW_TABLES:
        connection.exec_driver_sql(definitions[table]["ddl"].replace(" BLOB", " BYTEA").replace(" DATETIME", " TIMESTAMP WITH TIME ZONE"))
        for statement in definitions[table]["indexes"]:
            connection.exec_driver_sql(statement)


def downgrade():
    raise RuntimeError("local_creator_preserves_user_sources_forward_only")
