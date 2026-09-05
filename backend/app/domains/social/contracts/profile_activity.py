"""World-scoped social activity values for public WorldCharacter profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

WorldCharacterSocialProfileTab = Literal["posts", "replies", "likes"]


class WorldCharacterSocialProfileError(Exception):
    reason_code = "world_character_social_profile_error"


class WorldCharacterSocialProfileNotFoundError(WorldCharacterSocialProfileError):
    reason_code = "target_profile_unavailable"


class WorldCharacterSocialProfileForbiddenError(WorldCharacterSocialProfileError):
    reason_code = "world_character_social_profile_forbidden"


class WorldCharacterSocialProfileValidationError(WorldCharacterSocialProfileError):
    reason_code = "world_character_social_profile_invalid_request"


@dataclass(frozen=True, slots=True)
class WorldCharacterSocialProfileQuery:
    world_id: str
    world_character_id: str
    current_user_id: str
    tab: WorldCharacterSocialProfileTab = "posts"
    limit: int = 10
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class WorldCharacterSocialProfileCounts:
    post_count: int
    reply_count: int
    liked_post_count: int
    received_like_count: int


@dataclass(frozen=True, slots=True)
class WorldCharacterSocialProfileMention:
    handle: str
    character_id: str
    name: str


@dataclass(frozen=True, slots=True)
class WorldCharacterSocialProfileMedia:
    id: int
    post_id: str
    media_type: str
    url: str
    alt_text: str
    model: str
    prompt_hash: str
    byte_size: int
    width: int
    height: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WorldCharacterSocialProfilePost:
    id: str
    world_id: str
    author_world_character_id: str
    author_name: str
    author_handle: str | None
    author_avatar_url: str | None
    title: str
    body: str
    post_type: str
    reply_to_post_id: str | None
    created_at: datetime
    reply_count: int
    like_count: int
    author_profile_capability: Literal["available", "unavailable"]
    mentioned_characters: tuple[WorldCharacterSocialProfileMention, ...] = ()
    media: tuple[WorldCharacterSocialProfileMedia, ...] = ()


@dataclass(frozen=True, slots=True)
class WorldCharacterSocialProfilePage:
    world_id: str
    world_character_id: str
    character_id: str
    counts: WorldCharacterSocialProfileCounts
    tab: WorldCharacterSocialProfileTab
    items: tuple[WorldCharacterSocialProfilePost, ...]
    next_cursor: str | None


__all__ = [
    "WorldCharacterSocialProfileCounts",
    "WorldCharacterSocialProfileError",
    "WorldCharacterSocialProfileForbiddenError",
    "WorldCharacterSocialProfileMedia",
    "WorldCharacterSocialProfileMention",
    "WorldCharacterSocialProfileNotFoundError",
    "WorldCharacterSocialProfilePage",
    "WorldCharacterSocialProfilePost",
    "WorldCharacterSocialProfileQuery",
    "WorldCharacterSocialProfileTab",
    "WorldCharacterSocialProfileValidationError",
]
