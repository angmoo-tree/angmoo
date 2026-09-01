"""HTTP presentation schemas for World-scoped social activity."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


__all__ = [
    "ManualSocialDeliveryRead",
    "ManualSocialFeedRead",
    "ManualSocialPostRead",
    "ManualSocialWritePostRead",
    "ManualSocialWriteRead",
    "OwnerManualPostWrite",
    "OwnerManualReplyWrite",
]
