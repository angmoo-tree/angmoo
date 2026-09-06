"""Durable scheduler lease model; shares the existing single ORM Base."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class RuntimeSchedulerLease(Base):
    __tablename__ = "runtime_scheduler_leases"
    __table_args__ = (
        CheckConstraint(
            "singleton_key = 'resident-tick-scheduler'",
            name="ck_runtime_scheduler_leases_singleton",
        ),
        CheckConstraint(
            "state IN ('starting','active','draining','stopped','failed')",
            name="ck_runtime_scheduler_leases_state",
        ),
        CheckConstraint(
            "fencing_epoch >= 0",
            name="ck_runtime_scheduler_leases_fencing_epoch",
        ),
        CheckConstraint(
            "last_tick_result IS NULL OR last_tick_result IN "
            "('success','no_action','partial','failed','skipped')",
            name="ck_runtime_scheduler_leases_tick_result",
        ),
    )

    singleton_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    installation_id: Mapped[str] = mapped_column(
        ForeignKey("installation_identities.installation_id"),
        nullable=False,
        unique=True,
    )
    lease_owner_id: Mapped[str | None] = mapped_column(String(128))
    fencing_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stopped", server_default="stopped"
    )
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sleep_gap_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_tick_window_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_tick_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_tick_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_tick_result: Mapped[str | None] = mapped_column(String(20))
    next_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    shutdown_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
