from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProfileImageQuotaReservation(Base):
    __tablename__ = "profile_image_quota_reservations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    quota_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    candidate_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    route_mode: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ProfileImageCandidate(Base):
    __tablename__ = "profile_image_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    draft_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_creation_drafts.id"), index=True
    )
    character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"), index=True)
    quota_reservation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("profile_image_quota_reservations.id"), index=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    bucket: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False, default="image/webp")
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    route_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    quota_reservation: Mapped[Optional[ProfileImageQuotaReservation]] = relationship()
