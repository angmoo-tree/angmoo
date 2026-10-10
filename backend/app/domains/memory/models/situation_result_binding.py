"""Append-only, non-textual normalization proof with receipt-owned lifetime."""
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MemorySituationResultBinding(Base):
    __tablename__ = "memory_situation_result_bindings"
    receipt_sequence: Mapped[int] = mapped_column(ForeignKey("memory_situation_receipts.sequence", ondelete="CASCADE"), primary_key=True)
    validation_revision: Mapped[str] = mapped_column(String(40), primary_key=True)
    rules_revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)
    recheck_run_id: Mapped[str | None] = mapped_column(ForeignKey("memory_situation_runs.id", ondelete="SET NULL"))
    proof: Mapped[dict] = mapped_column(JSON, nullable=False)
