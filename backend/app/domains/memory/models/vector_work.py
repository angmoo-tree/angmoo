"""Durable projection intent. No source text, credentials or vector payloads."""
from sqlalchemy import Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MemoryVectorWork(Base):
    __tablename__ = "memory_vector_work"
    __table_args__ = (Index("ix_memory_vector_work_due", "generation", "state", "due_at"),)
    generation: Mapped[str] = mapped_column(String(80), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), index=True)
    desired_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    applied_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_change: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    due_at: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    last_code: Mapped[str | None] = mapped_column(String(80))
    preparation_key: Mapped[str | None] = mapped_column(String(64))


class MemoryVectorChange(Base):
    __tablename__ = "memory_vector_changes"
    __table_args__ = (
        UniqueConstraint("root_sequence", "source_kind", "source_key", name="uq_memory_vector_change_frontier"),
        Index("ix_memory_vector_changes_pending", "state", "sequence"),
        {"sqlite_autoincrement": True},
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    root_sequence: Mapped[int | None] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    cursor: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")


class MemoryVectorRevision(Base):
    __tablename__ = "memory_vector_validation_revisions"
    scope_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class MemoryVectorDependency(Base):
    __tablename__ = "memory_vector_dependencies"
    __table_args__ = (Index("ix_memory_vector_dependency_source", "source_kind", "source_key", "item_id"),)
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(80), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), primary_key=True)


class MemoryVectorMaintenance(Base):
    __tablename__ = "memory_vector_maintenance"
    generation: Mapped[str] = mapped_column(String(80), primary_key=True)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    cursor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    upper_bound: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    cutoff: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[float] = mapped_column(Float, nullable=False, default=0)


class MemoryVectorAttempt(Base):
    """Physical-call budget survives disposable generation loss."""
    __tablename__ = "memory_vector_attempts"
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[str] = mapped_column(String(128), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    credential_revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str | None] = mapped_column(String(24))
    retry_after: Mapped[float] = mapped_column(Float, nullable=False)
