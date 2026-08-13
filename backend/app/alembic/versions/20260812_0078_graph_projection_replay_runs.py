"""add graph projection replay audit runs

Revision ID: 20260812_0078
Revises: 20260811_0077
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_0078"
down_revision: str | None = "20260811_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "graph_projection_replay_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("source_event_id", sa.String(length=64), nullable=True),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("high_water_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("high_water_outbox_id", sa.String(length=64), nullable=True),
        sa.Column("total_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("noop_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_class", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('world_rebuild','event_reprocess','dead_retry')",
            name="ck_graph_projection_replay_runs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_graph_projection_replay_runs_status",
        ),
        sa.CheckConstraint(
            "(mode = 'world_rebuild' AND source_event_id IS NULL) OR "
            "(mode IN ('event_reprocess','dead_retry') AND source_event_id IS NOT NULL)",
            name="ck_graph_projection_replay_runs_source",
        ),
        sa.CheckConstraint(
            "total_count >= 0 AND applied_count >= 0 AND noop_count >= 0 "
            "AND failed_count >= 0",
            name="ck_graph_projection_replay_runs_counts",
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["social_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_graph_projection_replay_runs_active_world_rebuild",
        "graph_projection_replay_runs",
        ["world_id"],
        unique=True,
        postgresql_where=sa.text(
            "mode = 'world_rebuild' AND status IN ('pending','running')"
        ),
    )
    op.create_index(
        "ix_graph_projection_replay_runs_world_created",
        "graph_projection_replay_runs",
        ["world_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.scalar(sa.text("SELECT count(*) FROM graph_projection_replay_runs"))
    if int(count or 0) > 0:
        raise RuntimeError(
            "cannot downgrade 0078 while graph projection replay audit rows exist"
        )
    op.drop_index(
        "ix_graph_projection_replay_runs_world_created",
        table_name="graph_projection_replay_runs",
    )
    op.drop_index(
        "uq_graph_projection_replay_runs_active_world_rebuild",
        table_name="graph_projection_replay_runs",
    )
    op.drop_table("graph_projection_replay_runs")
