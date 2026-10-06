from urllib.parse import urlsplit


def validate_profile_media_reference(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return ""
    parsed = urlsplit(trimmed)
    if (
        parsed.scheme
        or parsed.netloc
        or trimmed.startswith("//")
        or not parsed.path.startswith("/media/")
    ):
        raise ValueError("Profile media must use an Angmoo-managed media path.")
    return trimmed


from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class LegacyReferenceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    character_id: str
    asset_id: str
    asset_revision: int
    asset_digest: str


class WorldGenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    appearance: str = Field(default="", max_length=1200)
    style: str = Field(default="", max_length=1200)
    negative: str = Field(default="", max_length=1800)
    reference_enabled: bool = False
    reference_asset_id: str | None = Field(default=None, max_length=64)
    reference_url: str | None = Field(default=None, max_length=500)
    legacy_reference: LegacyReferenceBinding | None = None
    profiles: dict = Field(default_factory=dict)


class WorldImagePolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    generation_limit: int | None = Field(default=None, ge=1, le=10000)
    vision_limit: int | None = Field(default=None, ge=1, le=10000)
    generation_enabled: bool | None = None
    vision_enabled: bool | None = None
    generation_settings: dict | None = None


class WorldImagePolicyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: str
    world_character_id: str
    revision: int = Field(ge=1)
    generation_limit: int | None
    vision_limit: int | None
    generation_enabled: bool
    vision_enabled: bool
    generation_settings: dict
    generation_usage: int = Field(ge=0)
    vision_usage: int = Field(ge=0)
    timezone: str
    reset_at: datetime
