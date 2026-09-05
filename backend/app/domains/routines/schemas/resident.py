"""Activity settings, logs and slots owned by routines."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.domains.routines.constants import MAX_COMMENTS_PER_DAY, MAX_POSTS_PER_DAY
from app.core.response_schemas import UtcInstantResponseModel
WritingRepetitionLevel = Literal["off", "light", "normal", "strong"]


class AgentActionRangeRead(BaseModel):
    min: int
    max: int
    label: str
    note: str = ""



class AgentActivitySettingRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    auto_enabled: bool
    activity_level: str
    activity_interval_minutes: int
    comment_cooldown_minutes: int
    max_comments_per_day: int
    post_cooldown_hours: int
    max_posts_per_day: int
    allow_post: bool
    allow_reply: bool
    allow_like: bool
    allow_repost: bool
    allow_follow: bool
    allow_unfollow: bool
    allow_observe: bool
    tendency_summary: str
    tendency_action_ranges: dict[str, AgentActionRangeRead]
    tendency_analysis_ready: bool = False
    tendency_updated_at: datetime | None = None
    tendency_error: str | None = None
    active_hours_start: str
    active_hours_end: str
    writing_temperature: float
    writing_repetition_level: WritingRepetitionLevel
    updated_at: datetime



class AgentActivitySummaryRead(UtcInstantResponseModel):
    within_active_hours: bool
    timezone: str = "Asia/Seoul"
    allowed_actions: list[str]
    blocked_reasons: dict[str, str]
    last_activity_at: datetime | None = None
    next_activity_at: datetime | None = None
    manual_run_available_at: datetime | None = None
    first_greeting_available_at: datetime | None = None
    today_comment_count: int
    max_comments_per_day: int
    today_post_count: int
    max_posts_per_day: int
    today_like_count: int





class AgentActivityLogRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    character_id: str
    action_type: str
    target_post_id: str | None = None
    target_profile_type: str | None = None
    target_profile_id: str | None = None
    target_profile_name: str | None = None
    target_profile_handle: str | None = None
    target_profile_avatar_url: str | None = None
    reason: str
    result: str
    created_at: datetime



class AgentSlotRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    status: str
    assigned_user_id: str | None = None
    assigned_character_id: str | None = None
    assigned_credential_id: str | None = None
    next_tick_at: datetime | None = None
    last_run_at: datetime | None = None
    heartbeat_interval_seconds: int | None = None
    locked_by_run_id: str | None = None
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime


class AgentActivitySettingUpdate(BaseModel):
    auto_enabled: bool | None = None
    activity_level: str | None = Field(default=None, max_length=20)
    activity_interval_minutes: int | None = Field(default=None, ge=30, le=1440)
    comment_cooldown_minutes: int | None = Field(default=None, ge=15, le=1440)
    max_comments_per_day: int | None = Field(
        default=None, ge=0, le=MAX_COMMENTS_PER_DAY
    )
    post_cooldown_hours: int | None = Field(default=None, ge=1, le=168)
    max_posts_per_day: int | None = Field(default=None, ge=0, le=MAX_POSTS_PER_DAY)
    allow_post: bool | None = None
    allow_reply: bool | None = None
    allow_like: bool | None = None
    allow_repost: bool | None = None
    allow_follow: bool | None = None
    allow_unfollow: bool | None = None
    allow_observe: bool | None = None
    active_hours_start: str | None = Field(default=None, max_length=5)
    active_hours_end: str | None = Field(default=None, max_length=5)
    writing_temperature: float | None = Field(
        default=None, ge=0.0, le=1.0, multiple_of=0.1
    )
    writing_repetition_level: WritingRepetitionLevel | None = None


class AgentFeedCueCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    manual_run: bool = False


class AgentFeedCueRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    character_id: str
    topic: str
    status: str
    consumed_run_id: str | None = None
    consumed_post_id: str | None = None
    created_at: datetime
    consumed_at: datetime | None = None
