"""Durable, content-free World erasure receipts and temporary cleanup journal."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class WorldDeletionRequest(Base):
    __tablename__ = "world_deletion_requests"
    __table_args__ = (UniqueConstraint("world_id"), UniqueConstraint("owner_id", "idempotency_key"),
                      Index("ix_world_deletion_work", "state", "next_attempt_at"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="accepted")
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="draining")
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __mapper_args__ = {"version_id_col": lease_epoch, "version_id_generator": False}


class WorldDeletionCleanupItem(Base):
    __tablename__ = "world_deletion_cleanup_items"
    __table_args__ = (UniqueConstraint("request_id", "kind", "item_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("world_deletion_requests.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Temporary exact row identities or managed relative paths, never source bodies/keys.
    reference: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
