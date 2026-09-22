"""Durable manual follow-up; memory and review work keep their own receipts."""
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base
from app.domains.relationships.models.social import JSON_DOCUMENT


class RelationshipReviewRequest(Base):
    __tablename__ = "relationship_review_requests"
    memory_request_id: Mapped[str] = mapped_column(ForeignKey("memory_consolidation_requests.id", ondelete="CASCADE"), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), index=True)
    canonical_request_id: Mapped[str | None] = mapped_column(ForeignKey("relationship_review_requests.memory_request_id"))
    state: Mapped[str] = mapped_column(String(32), default="waiting_memory", index=True)
    # IDs/digests only. Summaries stay in canonical memory and existing review manifests.
    snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    work_ids: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)
    last_code: Mapped[str | None] = mapped_column(String(100))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
