"""Allow separate observers to project the same source event.

Revision ID: 20260924_0098
Revises: 20260923_0097
"""

from alembic import op
from sqlalchemy import text

from app.runtime.migrations.sqlite_versions import observation_outbox_v20 as frozen


revision = "20260924_0098"
down_revision = "20260923_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("observation_outbox_online_migration_required")
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        frozen.upgrade(connection)
        return
    if connection.dialect.name != "postgresql":
        raise RuntimeError("observation_outbox_dialect_unsupported")

    before = frozen.capture_delta(connection)
    frozen.backfill_postgresql(connection)
    op.drop_constraint(
        "uq_graph_projection_outbox_event", "graph_projection_outbox", type_="unique"
    )
    op.create_check_constraint(
        "ck_graph_projection_outbox_observation_identity",
        "graph_projection_outbox",
        "NOT (projection_type = 'relationship_state' AND "
        "payload_version = 'relationship-observation-v1') OR "
        "(source_event_id IS NOT NULL AND relationship_state_id IS NOT NULL)",
    )
    op.create_index(
        "uq_graph_projection_outbox_observation", "graph_projection_outbox",
        ["projection_type", "source_event_id", "payload_version", "relationship_state_id"],
        unique=True,
        postgresql_where=text("projection_type = 'relationship_state' AND payload_version = 'relationship-observation-v1'"),
    )
    op.create_index(
        "uq_graph_projection_outbox_source_event", "graph_projection_outbox",
        ["projection_type", "source_event_id", "payload_version"],
        unique=True,
        postgresql_where=text("source_event_id IS NOT NULL AND NOT (projection_type = 'relationship_state' AND payload_version = 'relationship-observation-v1')"),
    )
    frozen.verify_delta(connection, before)


def downgrade() -> None:
    raise RuntimeError("observation_outbox_identity_is_forward_only")
