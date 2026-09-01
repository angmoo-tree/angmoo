from __future__ import annotations

from dataclasses import asdict
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.world_characters.domain.owner_controlled_identity import (
    OwnerControlledIdentitySnapshot,
    OwnerControlledProfile,
)
from app.domains.world_characters.domain.public_profile import (
    WorldCharacterPublicProfile,
)
from app.domains.world_characters.domain.studio_surface import StudioWorldCharacter
from app.domains.world_characters.domain.studio_lifecycle import (
    StudioCharacterCandidate,
)


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


class OwnerControlledProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    avatar_url: str = Field(min_length=1, max_length=500)
    intro: str = Field(min_length=1, max_length=280)
    role_key: str | None = Field(default=None, min_length=1, max_length=64)
    preferred_address: str = Field(default="", max_length=80)
    interests: list[str] = Field(default_factory=list, max_length=12)
    background: str = Field(default="", max_length=500)

    @field_validator(
        "display_name",
        "avatar_url",
        "intro",
        "role_key",
        "preferred_address",
        "background",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _clean(value)
        return normalized

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("avatar_url must be an http or https URL")
        return value

    @field_validator("interests")
    @classmethod
    def normalize_interests(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = _clean(value)
            key = normalized.casefold()
            if not normalized or len(normalized) > 64 or key in seen:
                continue
            seen.add(key)
            result.append(normalized)
        return result

    def domain_profile(self) -> OwnerControlledProfile:
        return OwnerControlledProfile(
            display_name=self.display_name,
            avatar_url=self.avatar_url,
            intro=self.intro,
            role_key=self.role_key,
            preferred_address=self.preferred_address,
            interests=tuple(self.interests),
            background=self.background,
        )


class OwnerControlledProfileRead(BaseModel):
    display_name: str
    avatar_url: str
    intro: str
    role_key: str | None
    preferred_address: str
    interests: list[str]
    background: str


class OwnerControlledIdentityRead(BaseModel):
    schema_version: Literal["owner-controlled-world-character-v1"] = (
        "owner-controlled-world-character-v1"
    )
    world_character_id: str
    world_id: str
    character_id: str
    control_mode: Literal["owner_controlled"]
    status: str
    autonomous_enabled: Literal[False]
    version: int
    profile: OwnerControlledProfileRead


class StudioWorldCharacterRead(BaseModel):
    world_character_id: str
    character_id: str
    display_name: str
    confirmation_name: str
    avatar_url: str | None
    intro: str
    role_key: str | None
    control_mode: Literal["autonomous", "owner_controlled"]
    status: str
    autonomous_enabled: bool
    selected_active_world: bool
    version: int
    activity_setup_state: Literal[
        "not_started",
        "generated",
        "approved",
        "unavailable_for_owner_controlled",
    ]

    @classmethod
    def from_snapshot(cls, snapshot: StudioWorldCharacter) -> "StudioWorldCharacterRead":
        return cls(**asdict(snapshot))


class StudioWorldCharacterListRead(BaseModel):
    schema_version: Literal["studio-world-character-list-v1"] = (
        "studio-world-character-list-v1"
    )
    world_id: str
    items: list[StudioWorldCharacterRead]


class StudioCharacterCandidateRead(BaseModel):
    character_id: str
    display_name: str
    handle: str | None
    avatar_url: str | None
    current_world_status: str | None
    eligible: bool
    reason_code: str | None

    @classmethod
    def from_snapshot(
        cls,
        snapshot: StudioCharacterCandidate,
    ) -> "StudioCharacterCandidateRead":
        return cls(**asdict(snapshot))


class StudioCharacterCandidateListRead(BaseModel):
    schema_version: Literal["studio-character-candidates-v1"] = (
        "studio-character-candidates-v1"
    )
    world_id: str
    items: list[StudioCharacterCandidateRead]


class WorldCharacterProfileRead(BaseModel):
    schema_version: Literal["world-character-profile-v1"] = (
        "world-character-profile-v1"
    )
    world_id: str
    world_character_id: str
    character_id: str
    display_name: str
    handle: str | None
    avatar_url: str | None
    banner_url: str | None
    intro: str
    role_key: str | None
    control_mode: Literal["autonomous", "owner_controlled"]
    status: Literal["active"]
    profile_capability: Literal["available"]

    @classmethod
    def from_snapshot(
        cls,
        snapshot: WorldCharacterPublicProfile,
    ) -> "WorldCharacterProfileRead":
        return cls(**asdict(snapshot))


class WorldCharacterProfileListRead(BaseModel):
    schema_version: Literal["world-character-profile-list-v1"] = (
        "world-character-profile-list-v1"
    )
    world_id: str
    items: list[WorldCharacterProfileRead]


def identity_read(
    snapshot: OwnerControlledIdentitySnapshot,
) -> OwnerControlledIdentityRead:
    return OwnerControlledIdentityRead(
        world_character_id=snapshot.world_character_id,
        world_id=snapshot.world_id,
        character_id=snapshot.character_id,
        control_mode="owner_controlled",
        status=snapshot.status,
        autonomous_enabled=False,
        version=snapshot.version,
        profile=OwnerControlledProfileRead(
            display_name=snapshot.profile.display_name,
            avatar_url=snapshot.profile.avatar_url,
            intro=snapshot.profile.intro,
            role_key=snapshot.profile.role_key,
            preferred_address=snapshot.profile.preferred_address,
            interests=list(snapshot.profile.interests),
            background=snapshot.profile.background,
        ),
    )


__all__ = [
    "OwnerControlledIdentityRead",
    "OwnerControlledProfileWrite",
    "StudioCharacterCandidateListRead",
    "StudioCharacterCandidateRead",
    "StudioWorldCharacterListRead",
    "StudioWorldCharacterRead",
    "WorldCharacterProfileListRead",
    "WorldCharacterProfileRead",
    "identity_read",
]
