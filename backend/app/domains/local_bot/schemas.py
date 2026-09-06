from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.domains.social.schemas.community import BotImageRequestRead, CommentRead, PostMediaRead
from app.core.response_schemas import UtcInstantResponseModel
from app.domains.characters.schemas import AgentExecutionMode

class AgentLocalConnectionRead(UtcInstantResponseModel):
    character_id: str
    execution_mode: AgentExecutionMode
    has_active_key: bool
    token_prefix: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None

class AgentLocalKeyCreateRead(BaseModel):
    connection: AgentLocalConnectionRead
    token: str

class BotCharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    handle: str
    avatar_url: str | None = None
    banner_url: str | None = None
    one_liner: str = ""
    status: str = "inactive"
    execution_mode: AgentExecutionMode = "local"

class BotMeRead(BaseModel):
    character: BotCharacterRead


class BotPostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    request_image: bool = False
    image_prompt: str | None = Field(default=None, max_length=1800)

    @model_validator(mode="after")
    def validate_image_request(self) -> "BotPostCreate":
        image_prompt = (self.image_prompt or "").strip()
        if self.request_image and not image_prompt:
            raise ValueError("image_prompt is required when request_image is true.")
        if not self.request_image and image_prompt:
            raise ValueError("image_prompt is only allowed when request_image is true.")
        self.image_prompt = image_prompt or None
        return self


class BotReplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=1000)


class BotFollowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["character"]
    target_id: str = Field(min_length=1, max_length=64)


class BotProfileRef(BaseModel):
    profile_type: Literal["character"]
    id: str
    display_name: str
    handle: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None


class BotFollowRead(BaseModel):
    follower: BotProfileRef
    target: BotProfileRef
    created_at: datetime


class BotProfileRead(BaseModel):
    profile: BotProfileRef
    execution_mode: Literal["llm", "local"] | None = None
    post_count: int
    reply_count: int = 0
    liked_post_count: int = 0
    received_like_count: int = 0
    follower_count: int
    character_follower_count: int = 0
    following_count: int
    one_liner: str | None = None


class BotStateSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    mood: str
    summary: str
    memory_note: str
    updated_at: datetime


class BotStateRead(BaseModel):
    state: BotStateSnapshot | None = None


class BotStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mood: str = Field(default="neutral", max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    memory_note: str = Field(default="", max_length=2000)
    observation_note: str | None = Field(default=None, max_length=1000)


class BotActivityLogRead(BaseModel):
    action_type: str
    target_post_id: str | None = None
    target_profile_type: str | None = None
    target_profile_id: str | None = None
    target_profile_name: str | None = None
    target_profile_handle: str | None = None
    target_profile_avatar_url: str | None = None
    created_at: datetime


class BotActivityLimitRead(BaseModel):
    action: str
    used_today: int
    max_per_day: int | None = None
    cooldown_seconds: int
    cooldown_remaining_seconds: int = 0
    retry_after_seconds: int | None = None


class BotActivityRead(BaseModel):
    recent_activity: list[BotActivityLogRead]
    limits: list[BotActivityLimitRead]


class BotNotificationRead(BaseModel):
    id: int
    notification_type: str
    post_id: str | None = None
    source_post_id: str | None = None
    actor_character_id: str | None = None
    actor_name: str | None = None
    actor_handle: str | None = None
    actor_avatar_url: str | None = None
    post_title: str | None = None
    post_body: str | None = None
    source_post_title: str | None = None
    source_post_body: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class BotPostReference(BaseModel):
    id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    created_at: datetime
    post_type: str = "post"
    author_character_id: str | None = None
    media: list[PostMediaRead] = Field(default_factory=list)


class BotPostSummary(BaseModel):
    id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    created_at: datetime
    post_type: str = "post"
    author_character_id: str | None = None
    reply_to_post_id: str | None = None
    quote_post_id: str | None = None
    repost_of_post_id: str | None = None
    comment_count: int
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    quoted_post: BotPostReference | None = None
    reposted_post: BotPostReference | None = None
    report_hidden: bool = False
    media: list[PostMediaRead] = Field(default_factory=list)


class BotPostDetail(BaseModel):
    id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    created_at: datetime
    post_type: str = "post"
    author_character_id: str | None = None
    reply_to_post_id: str | None = None
    quote_post_id: str | None = None
    repost_of_post_id: str | None = None
    comments: list[CommentRead]
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    quoted_post: BotPostReference | None = None
    reposted_post: BotPostReference | None = None
    report_hidden: bool = False
    media: list[PostMediaRead] = Field(default_factory=list)
    image_request: BotImageRequestRead | None = None


class BotFeedPage(BaseModel):
    items: list[BotPostSummary]
    next_cursor: str | None = None


class BotPostThreadRead(BaseModel):
    post: BotPostDetail
    replies: list[BotPostSummary]


class BotNotificationPage(BaseModel):
    items: list[BotNotificationRead]
    next_cursor: str | None = None
