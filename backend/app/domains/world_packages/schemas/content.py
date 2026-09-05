"""Portable content documents for World Package v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


SHA256_PATTERN = r"^[0-9a-f]{64}$"
ASSET_PATH_PATTERN = r"^assets/sha256-[0-9a-f]{64}\.webp$"


class WorldPackageContentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PortablePlace(WorldPackageContentSchema):
    ref: str = Field(pattern=r"^places/[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    available_dayparts: list[Literal["dawn", "morning", "afternoon", "evening"]] = Field(default_factory=list, max_length=4)
    access_role_refs: list[str] = Field(default_factory=list, max_length=20)


class PortableRole(WorldPackageContentSchema):
    ref: str = Field(pattern=r"^roles/[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    responsibilities: list[str] = Field(default_factory=list, max_length=12)
    allowed_activity_scope: list[str] = Field(default_factory=list, max_length=12)
    autonomous_allowed: bool = True


class PortableDaypartProfile(WorldPackageContentSchema):
    daypart: Literal["dawn", "morning", "afternoon", "evening"]
    description: str = Field(default="", max_length=500)
    available_features: list[str] = Field(default_factory=list, max_length=12)
    restricted_features: list[str] = Field(default_factory=list, max_length=12)


class PortableRule(WorldPackageContentSchema):
    ref: str = Field(pattern=r"^rules/[a-z][a-z0-9-]{0,63}$")
    rule_kind: Literal["allow", "forbid"]
    description: str = Field(min_length=1, max_length=500)


class PortableGlossaryTerm(WorldPackageContentSchema):
    ref: str = Field(pattern=r"^glossary/[a-z][a-z0-9-]{0,63}$")
    term: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=500)


class PortableWorldDefinition(WorldPackageContentSchema):
    schema_version: Literal["world-content-v1"]
    ref: Literal["world"]
    name: str = Field(min_length=2, max_length=120)
    tagline: str = Field(default="", max_length=160)
    setting_description: str = Field(default="", max_length=4000)
    daily_life_description: str = Field(default="", max_length=3000)
    genre_tags: list[str] = Field(default_factory=list, max_length=5)
    tone_tags: list[str] = Field(default_factory=list, max_length=5)
    timezone: str = Field(min_length=1, max_length=64)
    language: str = Field(min_length=2, max_length=16)
    additional_generation_guidance: str = Field(default="", max_length=1000)
    places: list[PortablePlace] = Field(default_factory=list, max_length=40)
    roles: list[PortableRole] = Field(default_factory=list, max_length=30)
    daypart_profiles: list[PortableDaypartProfile] = Field(default_factory=list, max_length=4)
    rules: list[PortableRule] = Field(default_factory=list, max_length=50)
    glossary: list[PortableGlossaryTerm] = Field(default_factory=list, max_length=100)
    banner_alt_text: str = Field(default="", max_length=500)
    banner_asset_ref: str | None = Field(default=None, pattern=ASSET_PATH_PATTERN)
    source_world_contract_version: str = Field(min_length=1, max_length=120)
    source_world_definition_hash: str = Field(pattern=SHA256_PATTERN)
    extensions: dict[str, JsonValue] = Field(default_factory=dict, max_length=32)


class AutonomousCharacterTemplate(WorldPackageContentSchema):
    ref: str = Field(pattern=r"^characters/[a-z][a-z0-9-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=120)
    handle_hint: str = Field(min_length=1, max_length=50)
    one_liner: str = Field(default="", max_length=200)
    personality: str = Field(default="", max_length=4000)
    speech_style: str = Field(default="", max_length=2000)
    worldview: str = Field(default="", max_length=3000)
    topic_preferences: list[str] = Field(default_factory=list, max_length=30)
    safety_rules: list[str] = Field(default_factory=list, max_length=30)
    persona_summary: str = Field(default="", max_length=2000)
    avatar_asset_ref: str | None = Field(default=None, pattern=ASSET_PATH_PATTERN)
    banner_asset_ref: str | None = Field(default=None, pattern=ASSET_PATH_PATTERN)
    extensions: dict[str, JsonValue] = Field(default_factory=dict, max_length=32)


class CharactersDocument(WorldPackageContentSchema):
    schema_version: Literal["characters-content-v1"]
    characters: list[AutonomousCharacterTemplate] = Field(max_length=50)

    @model_validator(mode="after")
    def _refs_are_unique(self) -> "CharactersDocument":
        refs = [item.ref for item in self.characters]
        if len(refs) != len(set(refs)):
            raise ValueError("character package-local refs must be unique")
        return self


class PortableWorldCharacterSeed(WorldPackageContentSchema):
    character_ref: str = Field(pattern=r"^characters/[a-z][a-z0-9-]{0,63}$")
    role_ref: str = Field(pattern=r"^roles/[a-z][a-z0-9-]{0,63}$")
    role_description: str = Field(default="", max_length=1000)
    background: str = Field(default="", max_length=3000)
    access_scope: list[str] = Field(default_factory=list, max_length=30)
    extensions: dict[str, JsonValue] = Field(default_factory=dict, max_length=32)


class WorldCharactersDocument(WorldPackageContentSchema):
    schema_version: Literal["world-characters-content-v1"]
    world_ref: Literal["world"]
    characters: list[PortableWorldCharacterSeed] = Field(max_length=50)

    @model_validator(mode="after")
    def _character_refs_are_unique(self) -> "WorldCharactersDocument":
        refs = [item.character_ref for item in self.characters]
        if len(refs) != len(set(refs)):
            raise ValueError("WorldCharacter seeds must reference each character once")
        return self


class ManagedImageAsset(WorldPackageContentSchema):
    ref: str = Field(pattern=ASSET_PATH_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=1, le=5 * 1024 * 1024)
    media_type: Literal["image/webp"]
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    alt_text: str = Field(default="", max_length=500)


class AssetIndexDocument(WorldPackageContentSchema):
    schema_version: Literal["assets-index-v1"]
    assets: list[ManagedImageAsset] = Field(max_length=100)

    @model_validator(mode="after")
    def _assets_are_unique_and_bounded(self) -> "AssetIndexDocument":
        refs = [item.ref for item in self.assets]
        if len(refs) != len(set(refs)):
            raise ValueError("asset refs must be unique")
        if sum(item.width * item.height for item in self.assets) > 200_000_000:
            raise ValueError("total decoded pixel budget exceeds 200 megapixels")
        return self
