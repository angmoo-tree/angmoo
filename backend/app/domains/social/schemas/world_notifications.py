"""Closed, World-scoped notification HTTP values; no arbitrary navigation URLs."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.core.response_schemas import UtcInstantResponseModel


class NotificationScopeRead(BaseModel):
    world_id: str
    recipient_world_character_id: str


class NotificationTargetRead(BaseModel):
    kind: Literal["post", "world_character"]
    post_id: str | None = None
    world_character_id: str | None = None
    can_open: bool


class WorldNotificationRead(UtcInstantResponseModel):
    id: int
    notification_type: Literal["like", "reply", "quote", "mention", "repost", "follow"]
    actor_world_character_id: str | None
    actor_name: str | None
    actor_handle: str | None
    actor_avatar_url: str | None
    actor_deleted: bool
    read_at: datetime | None
    created_at: datetime
    preview_text: str | None
    target: NotificationTargetRead


class WorldNotificationCountRead(UtcInstantResponseModel):
    scope: NotificationScopeRead
    unread_count: int = Field(ge=0)


class WorldNotificationPage(WorldNotificationCountRead):
    items: list[WorldNotificationRead]
    next_cursor: str | None


class WorldNotificationReadResult(WorldNotificationCountRead):
    notification_id: int
    read_at: datetime


class WorldNotificationReadAllRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    recipient_world_character_id: str = Field(min_length=1, max_length=64)


class WorldNotificationReadAllResult(WorldNotificationCountRead):
    marked_count: int = Field(ge=0)
    read_at: datetime | None
    through_notification_id: int | None = Field(ge=1)


class WorldUnreadCountItem(BaseModel):
    world_id: str
    recipient_world_character_id: str | None
    status: Literal["available", "unavailable"]
    unread_count: int | None = Field(ge=0)


class WorldUnreadCountsRead(BaseModel):
    items: list[WorldUnreadCountItem]
