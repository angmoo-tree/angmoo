from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SiteOperationBanner(Base):
    __tablename__ = "site_operation_banners"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blocks_auto_ticks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocks_run_now: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocks_feed_cues: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    updated_by: Mapped[Optional["User"]] = relationship()


class SiteOperationSetting(Base):
    __tablename__ = "site_operation_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    updated_by: Mapped[Optional["User"]] = relationship()


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    admin_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON)
    request_ip: Mapped[Optional[str]] = mapped_column(String(80))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    admin_user: Mapped["User"] = relationship()
