from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import active_hours
from app.core.agent_activity_limits import (
    DEFAULT_MAX_COMMENTS_PER_DAY,
    DEFAULT_MAX_POSTS_PER_DAY,
)
from app.core.db import Base
from app.core.image_generation import (
    DEFAULT_MAX_IMAGES_PER_DAY,
    DEFAULT_POLLINATIONS_IMAGE_MODEL,
)


class AgentActivitySetting(Base):
    __tablename__ = "agent_activity_settings"
    __table_args__ = (
        CheckConstraint(
            "writing_repetition_level in ('off', 'light', 'normal', 'strong')",
            name="ck_agent_activity_settings_writing_repetition_level",
        ),
    )

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    auto_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    activity_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    comment_cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    max_comments_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_COMMENTS_PER_DAY
    )
    post_cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    max_posts_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_POSTS_PER_DAY
    )
    like_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    allow_post: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_like: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_repost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_follow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_unfollow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_observe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tendency_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tendency_action_ranges: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    planner_tendency_profile: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    tendency_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tendency_error: Mapped[str | None] = mapped_column(Text)
    active_hours_start: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default=active_hours.DEFAULT_ACTIVE_HOURS_START,
    )
    active_hours_end: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default=active_hours.DEFAULT_ACTIVE_HOURS_END,
    )
    autonomy_level: Mapped[str] = mapped_column(String(20), nullable=False, default="balanced")
    writing_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    writing_presence_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    writing_repetition_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="light"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped["Character"] = relationship(back_populates="activity_setting")

    @property
    def tendency_analysis_ready(self) -> bool:
        profile = (
            self.planner_tendency_profile
            if isinstance(self.planner_tendency_profile, dict)
            else {}
        )
        criteria = profile.get("feed_seed_interest_criteria")
        return bool(
            self.tendency_updated_at
            and self.tendency_summary.strip()
            and self.tendency_action_ranges
            and isinstance(criteria, str)
            and criteria.strip()
        )


class AgentImageGenerationSetting(Base):
    __tablename__ = "agent_image_generation_settings"

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    encrypted_openrouter_api_key: Mapped[str | None] = mapped_column(Text)
    encrypted_pollinations_api_key: Mapped[str | None] = mapped_column(Text)
    encrypted_replicate_api_token: Mapped[str | None] = mapped_column(Text)
    key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    replicate_key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    image_key_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="disabled"
    )
    image_generation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    max_images_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_IMAGES_PER_DAY
    )
    openrouter_image_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="black-forest-labs/flux.2-klein-4b"
    )
    pollinations_image_model: Mapped[str] = mapped_column(
        String(80), nullable=False, default=DEFAULT_POLLINATIONS_IMAGE_MODEL
    )
    seed_image_url: Mapped[str | None] = mapped_column(String(500))
    visual_identity_prompt: Mapped[str | None] = mapped_column(Text)
    visual_identity_source_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped["Character"] = relationship(
        back_populates="image_generation_setting"
    )
