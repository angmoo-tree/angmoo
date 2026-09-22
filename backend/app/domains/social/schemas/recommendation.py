from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TopicDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    scope: Literal["common", "world"]


class TopicGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[TopicDefinition] = Field(max_length=64)


class TopicRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=64)


class TopicKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_character_id: str | None = None


FeedLane = Literal["latest", "interest", "relation", "explore"]
FeedAction = Literal["like", "comment", "repost", "follow"]
FeedResult = Literal["unrecorded", "no_action", "not_selected", "selected", "pending", "succeeded", "failed", "not_performed"]


class DeliveryPostRead(BaseModel):
    post_id: str
    title: str = Field(max_length=160)
    lane: FeedLane | None
    sources: list[FeedLane] = Field(max_length=4)
    selected_action: FeedAction | None
    result_state: FeedResult


class DeliveryHistoryRead(BaseModel):
    delivery_id: str
    recorded_at: str
    recorded_post_count: int | None = Field(ge=0)
    visible_post_count: int = Field(ge=0, le=20)
    unavailable_post_count: int | None = Field(ge=0)
    is_partial: bool
    posts: list[DeliveryPostRead] = Field(max_length=20)


class TopicRead(BaseModel):
    id: str
    name: str
    scope: Literal["common", "world"]


class LegacyFeedRead(BaseModel):
    post_id: str
    title: str = Field(max_length=160)
    sources: list[FeedLane] = Field(max_length=4)
    lane: FeedLane | None
    outcome: Literal["action_selected", "no_action", "not_selected"] | None
    action: FeedAction | None


from app.domains.social.schemas.feed_status import FeedStatusRead


class RecommendationTopicsRead(BaseModel):
    feed_status: FeedStatusRead | None = None
    world_id: str
    world_character_id: str | None
    state: Literal["pending", "running", "ready", "failed", "stale"]
    topics: list[TopicRead]
    key_world_character_id: str | None
    model: str
    thinking_level: str
    last_code: str | None
    approval_required: bool
    recent_deliveries: list[DeliveryHistoryRead] = Field(max_length=5)
    recent_feed: list[LegacyFeedRead] = Field(max_length=20)
