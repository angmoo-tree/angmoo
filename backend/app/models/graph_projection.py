from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class GraphProjectionReplayRun(Base):
    __tablename__ = "graph_projection_replay_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('world_rebuild','event_reprocess','dead_retry')",
            name="ck_graph_projection_replay_runs_mode",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_graph_projection_replay_runs_status",
        ),
        CheckConstraint(
            "(mode = 'world_rebuild' AND source_event_id IS NULL) OR "
            "(mode IN ('event_reprocess','dead_retry') AND source_event_id IS NOT NULL)",
            name="ck_graph_projection_replay_runs_source",
        ),
        CheckConstraint(
            "total_count >= 0 AND applied_count >= 0 AND noop_count >= 0 "
            "AND failed_count >= 0",
            name="ck_graph_projection_replay_runs_counts",
        ),
        Index(
            "uq_graph_projection_replay_runs_active_world_rebuild",
            "world_id",
            unique=True,
            postgresql_where=text(
                "mode = 'world_rebuild' AND status IN ('pending','running')"
            ),
        ),
        Index(
            "ix_graph_projection_replay_runs_world_created",
            "world_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("social_events.id")
    )
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    high_water_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    high_water_outbox_id: Mapped[str | None] = mapped_column(String(64))
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    noop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
