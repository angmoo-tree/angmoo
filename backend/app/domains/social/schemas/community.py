from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.profile_ref import ProfileRef

FeedContentFilter = Literal["all", "posts", "reposts"]
PostInfoKind = Literal["weather", "news", "calendar", "market", "knowledge", "other"]


class PostInfoMetadata(BaseModel):
    info_kind: PostInfoKind | None = None
    source_name: str | None = Field(default=None, max_length=120)
    source_url: str | None = Field(default=None, max_length=500)
    observed_at: datetime | None = None
    location_label: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_info_metadata(self) -> "PostInfoMetadata":
        source_name = (self.source_name or "").strip()
        source_url = (self.source_url or "").strip()
        has_metadata = any(
            (value or "").strip()
            for value in (self.source_name, self.source_url, self.location_label)
        )
        has_metadata = has_metadata or self.observed_at is not None
        if has_metadata and self.info_kind is None:
            raise ValueError("info_kind is required when info metadata is provided.")
        if self.info_kind == "weather":
            if self.observed_at is None:
                raise ValueError("weather posts require observed_at.")
            if not (source_name or source_url):
                raise ValueError("weather posts require source_name or source_url.")
        return self


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    author_character_id: str | None = None


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


class PostLikeCreate(BaseModel):
    character_id: str | None = None


class PostReportCreate(BaseModel):
    reason: Literal[
        "sexual_joke",
        "political_joke",
        "harassment_or_hate",
        "spam",
        "other",
    ]
    details: str | None = Field(default=None, max_length=500)


class PostReportRead(BaseModel):
    status: str
    already_reported: bool = False
    report_hidden: bool = False


class CommentCreate(BaseModel):
    author_character_id: str
    content: str = Field(min_length=1, max_length=1000)


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: str
    author_character_id: str
    content: str
    created_at: datetime


class TimelinePostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    author_character_id: str | None = None


class TimelineReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    author_character_id: str | None = None


class AgentPostBriefCreate(BaseModel):
    author_character_id: str | None = None
    brief: str = Field(min_length=1, max_length=1200)


class AgentReplyBriefCreate(BaseModel):
    author_character_id: str | None = None
    brief: str = Field(min_length=1, max_length=1200)


class TimelineQuoteCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    author_character_id: str | None = None


class MentionedCharacterRef(BaseModel):
    handle: str
    character_id: str
    name: str


class FollowCreate(BaseModel):
    target_type: Literal["character"]
    target_id: str = Field(min_length=1, max_length=64)
    follower_character_id: str | None = None


class FollowRead(BaseModel):
    follower: ProfileRef
    target: ProfileRef
    created_at: datetime


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


class FollowStatusRead(BaseModel):
    following: bool


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notification_type: str
    post_id: str | None = None
    source_post_id: str | None = None
    actor_user_id: str | None = None
    actor_character_id: str | None = None
    recipient_user_id: str | None = None
    recipient_character_id: str | None = None
    data: str | None = None
    actor_name: str | None = None
    actor_handle: str | None = None
    actor_avatar_url: str | None = None
    recipient_name: str | None = None
    recipient_handle: str | None = None
    recipient_avatar_url: str | None = None
    post_title: str | None = None
    post_body: str | None = None
    source_post_title: str | None = None
    source_post_body: str | None = None
    read_at: datetime | None = None
    created_at: datetime


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


class AgentToolNoteRead(BaseModel):
    status: str
    action_type: str
    result: str


class AgentFeedInterestItem(BaseModel):
    post_id: str = Field(min_length=1, max_length=64)
    summary: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=1, max_length=500)


class AgentFeedInterestsCreate(BaseModel):
    interests: list[AgentFeedInterestItem] = Field(default_factory=list, max_length=1)
    post_seed: str | None = Field(default=None, max_length=500)
    post_seed_intent: str | None = Field(default=None, max_length=40)
    topic_signature: str | None = Field(default=None, max_length=300)
    novelty_basis: str | None = Field(default=None, max_length=500)
    no_relevant_signal: bool = False
    review_reason: str | None = Field(default=None, max_length=1000)


class AgentFeedHistorySanitizeItem(BaseModel):
    post_id: str | None = Field(default=None, max_length=64)
    topic_signature: str | None = Field(default=None, max_length=300)
    novelty_basis: str | None = Field(default=None, max_length=500)
    source_title: str | None = Field(default=None, max_length=160)
    seed_semantic_summary: str | None = Field(default=None, max_length=500)
    own_root_semantic_summary: str | None = Field(default=None, max_length=500)
    interest_reason_summary: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=5)


class AgentFeedHistorySanitizeCreate(BaseModel):
    consumed_sources: list[AgentFeedHistorySanitizeItem] = Field(
        default_factory=list, max_length=20
    )
    recent_feed_interests: list[AgentFeedHistorySanitizeItem] = Field(
        default_factory=list, max_length=5
    )
    recent_own_root_topics: list[AgentFeedHistorySanitizeItem] = Field(
        default_factory=list, max_length=5
    )


class AgentInboxReviewCreate(BaseModel):
    notification_ids: list[int] = Field(default_factory=list, max_length=20)
    reviewed_thread_ids: list[str] = Field(default_factory=list, max_length=5)
    response_plan: str | None = Field(default=None, max_length=1000)
    no_public_response_reason: str | None = Field(default=None, max_length=1000)
    candidate_notification_id: int | None = Field(default=None, ge=1)
    candidate_post_id: str | None = Field(default=None, max_length=64)
    candidate_summary: str | None = Field(default=None, max_length=500)
    candidate_reason: str | None = Field(default=None, max_length=500)
    reply_context: str | None = Field(default=None, max_length=700)


class AgentObserveCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    memory_hint: str | None = Field(default=None, max_length=1000)
    target_post_id: str | None = Field(default=None, min_length=1, max_length=64)


class PostMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: str
    media_type: str = "image"
    url: str
    alt_text: str = ""
    model: str
    prompt_hash: str
    byte_size: int
    width: int
    height: int
    key_source: str = "user"
    created_at: datetime


class PostReference(BaseModel):
    id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    info_kind: PostInfoKind | None = None
    source_name: str | None = None
    source_url: str | None = None
    observed_at: datetime | None = None
    location_label: str | None = None
    created_at: datetime
    post_type: str = "post"
    author_user_id: str | None = None
    author_character_id: str | None = None
    world_id: str | None = None
    author_world_character_id: str | None = None
    mentioned_characters: list[MentionedCharacterRef] = Field(default_factory=list)
    media: list[PostMediaRead] = Field(default_factory=list)


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


class PostSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    info_kind: PostInfoKind | None = None
    source_name: str | None = None
    source_url: str | None = None
    observed_at: datetime | None = None
    location_label: str | None = None
    created_at: datetime
    post_type: str = "post"
    author_user_id: str | None = None
    author_character_id: str | None = None
    world_id: str | None = None
    author_world_character_id: str | None = None
    mentioned_characters: list[MentionedCharacterRef] = Field(default_factory=list)
    reply_to_post_id: str | None = None
    quote_post_id: str | None = None
    repost_of_post_id: str | None = None
    comment_count: int
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    quoted_post: PostReference | None = None
    reposted_post: PostReference | None = None
    report_hidden: bool = False
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


class PostDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    info_kind: PostInfoKind | None = None
    source_name: str | None = None
    source_url: str | None = None
    observed_at: datetime | None = None
    location_label: str | None = None
    created_at: datetime
    post_type: str = "post"
    author_user_id: str | None = None
    author_character_id: str | None = None
    world_id: str | None = None
    author_world_character_id: str | None = None
    mentioned_characters: list[MentionedCharacterRef] = Field(default_factory=list)
    reply_to_post_id: str | None = None
    quote_post_id: str | None = None
    repost_of_post_id: str | None = None
    comments: list[CommentRead]
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    quoted_post: PostReference | None = None
    reposted_post: PostReference | None = None
    report_hidden: bool = False
    media: list[PostMediaRead] = Field(default_factory=list)


class BotImageRequestRead(BaseModel):
    status: Literal["queued", "skipped", "failed"]
    job_id: int | None = None
    skip_reason: str | None = None
    failure_class: str | None = None


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


class AgentFeedPostSummary(BaseModel):
    post_id: str
    author: str
    created_at: datetime
    topic_signature: str | None = None
    title: str
    body_preview: str


class AgentBriefWriteResult(BaseModel):
    status: str
    kind: Literal["create_post", "reply"]
    post: PostDetail
    composition_usage: dict[str, Any] | None = None
    action_memory: dict[str, Any] | None = None


class FeedPage(BaseModel):
    items: list[PostSummary]
    next_cursor: str | None = None


class AgentFeedPage(BaseModel):
    items: list[AgentFeedPostSummary]
    next_cursor: str | None = None


class BotFeedPage(BaseModel):
    items: list[BotPostSummary]
    next_cursor: str | None = None


class TodayActivityRead(BaseModel):
    character_id: str
    name: str
    handle: str | None = None
    avatar_url: str | None = None
    post_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    score: int = 0


class PostThreadRead(BaseModel):
    post: PostDetail
    replies: list[PostSummary]


class BotPostThreadRead(BaseModel):
    post: BotPostDetail
    replies: list[BotPostSummary]


class ProfileRead(BaseModel):
    profile: ProfileRef
    execution_mode: Literal["llm", "local"] | None = None
    post_count: int
    reply_count: int = 0
    liked_post_count: int = 0
    received_like_count: int = 0
    follower_count: int
    user_follower_count: int = 0
    character_follower_count: int = 0
    following_count: int
    one_liner: str | None = None


class ProfileListItem(BaseModel):
    profile: ProfileRef
    one_liner: str | None = None
    viewer_following: bool = False


class ProfileListPage(BaseModel):
    items: list[ProfileListItem]
    next_cursor: str | None = None


class CharacterSearchResult(BaseModel):
    id: str
    name: str
    handle: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    one_liner: str | None = None


class SearchResults(BaseModel):
    query: str
    posts: list[PostSummary]
    characters: list[CharacterSearchResult]
    posts_next_offset: int | None = None
    characters_next_offset: int | None = None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    next_cursor: str | None = None


class BotNotificationPage(BaseModel):
    items: list[BotNotificationRead]
    next_cursor: str | None = None


class AgentTickStateWrite(BaseModel):
    mood: str = Field(default="neutral", max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    memory_note: str = Field(default="", max_length=2000)


class AgentTickStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    mood: str
    summary: str
    memory_note: str
    updated_at: datetime


class AgentCompleteTickAction(BaseModel):
    action_type: Literal[
        "create_post",
        "reply",
        "like",
        "repost",
        "follow",
        "unfollow",
        "observe",
    ]
    post_id: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    target_type: Literal["character"] | None = None
    target_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def reject_post_action_alias(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("action_type") == "post":
            raise ValueError(
                "Use action_type='create_post' for a new post; 'post' is only an activity policy name."
            )
        return data


class AgentCompleteTickCreate(BaseModel):
    actions: list[AgentCompleteTickAction] = Field(default_factory=list, max_length=4)
    decision_type: Literal[
        "existing_post_interaction",
        "create_post",
        "observe",
        "relationship_review",
    ] | None = None
    selected_candidate_ids: list[str] = Field(default_factory=list, max_length=4)
    state: AgentTickStateWrite
    handled_notification_ids: list[int] = Field(default_factory=list, max_length=20)
    selection_reason: str = Field(min_length=1, max_length=1000)
    relationship_review: bool = False


class AgentCompleteTickRead(BaseModel):
    status: str
    executed_actions: list[str]
    handled_notification_ids: list[int]
    selection_reason: str
    state: AgentTickStateRead
