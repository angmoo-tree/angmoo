from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


LOCAL_BOT_ACTION_LABELS = (
    "follow",
    "like",
    "post",
    "reaction",
    "reply",
    "repost",
    "state",
    "unfollow",
)


class LocalBotActionQuotaBucket(Base):
    __tablename__ = "local_bot_action_quota_buckets"
    __table_args__ = (
        CheckConstraint(
            "action_label IN "
            "('follow','like','post','reaction','reply','repost','state','unfollow')",
            name="ck_local_bot_action_quota_label",
        ),
        CheckConstraint(
            "used_count >= 0",
            name="ck_local_bot_action_quota_used_nonnegative",
        ),
    )

    character_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    action_label: Mapped[str] = mapped_column(String(24), primary_key=True)
    quota_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_succeeded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class LocalBotReadQuotaBucket(Base):
    __tablename__ = "local_bot_read_quota_buckets"
    __table_args__ = (
        CheckConstraint(
            "used_count >= 0",
            name="ck_local_bot_read_quota_used_nonnegative",
        ),
    )

    local_key_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("agent_local_keys.id", ondelete="CASCADE"),
        primary_key=True,
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
