"""HTTP presentation schemas for World-scoped social activity."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfilePage,
)


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


class OwnerManualPostWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("title", "body")
    @classmethod
    def normalize(cls, value: str) -> str:
        return _clean(value)


class OwnerManualReplyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def normalize(cls, value: str) -> str:
        return _clean(value)


class ManualSocialWritePostRead(BaseModel):
    id: str
    world_id: str
    author_world_character_id: str
    author_name: str
    author_handle: str | None = None
    author_avatar_url: str | None = None
    title: str
    body: str
    post_type: str
    reply_to_post_id: str | None
    created_at: datetime
    can_owner_reply: bool = False
    author_profile_capability: Literal["available", "unavailable"] = "available"


class ManualSocialPostRead(ManualSocialWritePostRead):
    reply_count: int = Field(ge=0)
    like_count: int = Field(ge=0)


class ManualSocialDeliveryRead(BaseModel):
    provider_call_count: Literal[0] = 0
    inbox_candidate_id: str | None = None
    inbox_status: Literal["not_applicable", "pending"]
    public_reaction_required: Literal[False] = False


class ManualSocialWriteRead(BaseModel):
    schema_version: Literal["owner-manual-social-v1"] = "owner-manual-social-v1"
    operation: Literal["post", "reply"]
    replayed: bool
    post: ManualSocialWritePostRead
    delivery: ManualSocialDeliveryRead


class ManualSocialFeedRead(BaseModel):
    schema_version: Literal["owner-manual-social-v1"] = "owner-manual-social-v1"
    world_id: str
    owner_world_character_id: str
    items: list[ManualSocialPostRead]


class WorldCharacterSocialProfileCountsRead(BaseModel):
    post_count: int = Field(ge=0)
    reply_count: int = Field(ge=0)
    liked_post_count: int = Field(ge=0)
    received_like_count: int = Field(ge=0)


class WorldCharacterSocialProfileMentionRead(BaseModel):
    handle: str
    character_id: str
    name: str


class WorldCharacterSocialProfileMediaRead(BaseModel):
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


class WorldCharacterSocialProfilePostRead(BaseModel):
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
    reply_count: int = Field(ge=0)
    like_count: int = Field(ge=0)
    author_profile_capability: Literal["available", "unavailable"]
    mentioned_characters: list[WorldCharacterSocialProfileMentionRead]
    media: list[WorldCharacterSocialProfileMediaRead]


class WorldCharacterSocialProfileRead(BaseModel):
    schema_version: Literal["world-character-social-profile-v1"] = (
        "world-character-social-profile-v1"
    )
    world_id: str
    world_character_id: str
    character_id: str
    counts: WorldCharacterSocialProfileCountsRead
    tab: Literal["posts", "replies", "likes"]
    items: list[WorldCharacterSocialProfilePostRead]
    next_cursor: str | None

    @classmethod
    def from_snapshot(
        cls,
        snapshot: WorldCharacterSocialProfilePage,
    ) -> WorldCharacterSocialProfileRead:
        return cls(
            world_id=snapshot.world_id,
            world_character_id=snapshot.world_character_id,
            character_id=snapshot.character_id,
            counts=WorldCharacterSocialProfileCountsRead(
                post_count=snapshot.counts.post_count,
                reply_count=snapshot.counts.reply_count,
                liked_post_count=snapshot.counts.liked_post_count,
                received_like_count=snapshot.counts.received_like_count,
            ),
            tab=snapshot.tab,
            items=[
                WorldCharacterSocialProfilePostRead(
                    id=item.id,
                    world_id=item.world_id,
                    author_world_character_id=item.author_world_character_id,
                    author_name=item.author_name,
                    author_handle=item.author_handle,
                    author_avatar_url=item.author_avatar_url,
                    title=item.title,
                    body=item.body,
                    post_type=item.post_type,
                    reply_to_post_id=item.reply_to_post_id,
                    created_at=item.created_at,
                    reply_count=item.reply_count,
                    like_count=item.like_count,
                    author_profile_capability=item.author_profile_capability,
                    mentioned_characters=[
                        WorldCharacterSocialProfileMentionRead(
                            handle=mention.handle,
                            character_id=mention.character_id,
                            name=mention.name,
                        )
                        for mention in item.mentioned_characters
                    ],
                    media=[
                        WorldCharacterSocialProfileMediaRead(
                            id=media.id,
                            post_id=media.post_id,
                            media_type=media.media_type,
                            url=media.url,
                            alt_text=media.alt_text,
                            model=media.model,
                            prompt_hash=media.prompt_hash,
                            byte_size=media.byte_size,
                            width=media.width,
                            height=media.height,
                            created_at=media.created_at,
                        )
                        for media in item.media
                    ],
                )
                for item in snapshot.items
            ],
            next_cursor=snapshot.next_cursor,
        )


__all__ = [
    "ManualSocialDeliveryRead",
    "ManualSocialFeedRead",
    "ManualSocialPostRead",
    "ManualSocialWritePostRead",
    "ManualSocialWriteRead",
    "OwnerManualPostWrite",
    "OwnerManualReplyWrite",
    "WorldCharacterSocialProfileCountsRead",
    "WorldCharacterSocialProfileMediaRead",
    "WorldCharacterSocialProfileMentionRead",
    "WorldCharacterSocialProfilePostRead",
    "WorldCharacterSocialProfileRead",
]
