"""Scoped management HTTP contracts; public reads never expose private persona."""
from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.domains.world_characters.schemas.identity import WorldCharacterProfileRead
from app.domains.characters.service.import_configuration import ImportProfile, ImportSettings
from app.domains.characters.contracts import PERSONA_LIMITS, normalize_persona_text


class WorldCharacterCapabilities(BaseModel):
    can_activate: bool
    can_deactivate: bool
    can_run_now: bool
    can_edit_profile: bool
    can_edit_settings: bool
    can_view_graph: bool
    reason: str | None


class DashboardStatus(BaseModel):
    state: Literal["user", "off", "running", "outside_hours", "error", "waiting", "capacity_wait", "not_ready"]
    reason: str | None = None


class DashboardActivitySettings(BaseModel):
    active_hours_start: str
    active_hours_end: str
    timezone: str
    activity_interval_minutes: int
    max_posts_per_day: int
    max_comments_per_day: int


class RecentWorldActivity(BaseModel):
    action_type: str
    occurred_at: str
    post_id: str | None
    title: str | None


class WorldCharacterDashboardItem(BaseModel):
    profile: WorldCharacterProfileRead
    revision: int
    autonomous_enabled: bool
    status: DashboardStatus
    settings: DashboardActivitySettings | None
    next_activity_at: str | None
    recent_activity: RecentWorldActivity | None
    capabilities: WorldCharacterCapabilities


class WorldCharacterSummary(BaseModel):
    total: int
    enabled: int
    disabled: int
    users: int


class WorldCharacterDashboardRead(BaseModel):
    contract_version: Literal["world-character-dashboard-v1"] = "world-character-dashboard-v1"
    world_id: str
    summary: WorldCharacterSummary
    items: list[WorldCharacterDashboardItem]


class WorldCharacterManagementRead(BaseModel):
    contract_version: Literal["world-character-management-v1"] = "world-character-management-v1"
    world_id: str
    world_character_id: str
    character_id: str
    item: WorldCharacterDashboardItem
    can_manage: bool


class WorldCharacterSettingsRead(BaseModel):
    contract_version: Literal["world-character-settings-v1"] = "world-character-settings-v1"
    world_id: str
    world_character_id: str
    revision: int
    profile: ImportProfile
    settings: ImportSettings
    capabilities: WorldCharacterCapabilities
    supported_generation_models: list["WorldModelOption"] = Field(default_factory=list)
    supported_image_models: list["WorldModelOption"] = Field(default_factory=list)


class WorldModelOption(BaseModel):
    value: str
    label: str
    enabled: bool
    reason: str | None = None


class ExpectedWorldRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class WorldCharacterProfilePatch(ExpectedWorldRevision):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    handle: str | None = Field(default=None, min_length=1, max_length=80)
    intro: str | None = Field(default=None, max_length=PERSONA_LIMITS["one_liner"])
    avatar_url: str | None = None
    banner_url: str | None = None


class WorldEditableSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    personality: str | None = Field(default=None, max_length=PERSONA_LIMITS["personality"])
    speech_style: str | None = Field(default=None, max_length=PERSONA_LIMITS["speech_style"])
    worldview: str | None = Field(default=None, max_length=PERSONA_LIMITS["worldview"])
    character_background: str | None = Field(default=None, max_length=PERSONA_LIMITS["character_background"])
    topic_preferences: str | None = Field(default=None, max_length=PERSONA_LIMITS["topic_preferences"])
    safety_rules: str | None = Field(default=None, max_length=PERSONA_LIMITS["safety_rules"])
    active_hours_start: str | None = None
    active_hours_end: str | None = None
    activity_interval_minutes: int | None = Field(default=None, ge=30, le=1440)
    max_posts_per_day: int | None = Field(default=None, ge=0, le=1000)
    max_comments_per_day: int | None = Field(default=None, ge=0, le=1000)
    generation_model: str | None = None
    image_model: str | None = None
    image_style: str | None = Field(default=None, max_length=10000)
    appearance_prompt: str | None = Field(default=None, max_length=10000)

    @field_validator("personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules", mode="before")
    @classmethod
    def _persona(cls, value):
        return normalize_persona_text(value) if isinstance(value, str) else value

    @field_validator("active_hours_start", "active_hours_end")
    @classmethod
    def _time(cls, value):
        if value is not None:
            if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):(?:00|30)|24:00", value):
                raise ValueError("world_active_hours_invalid")
        return value


class WorldCharacterSettingsPatch(ExpectedWorldRevision):
    settings: WorldEditableSettings


class WorldCharacterProfileMedia(ExpectedWorldRevision):
    media_type: Literal["avatar", "banner"]
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_base64: str = Field(min_length=1, max_length=16000000)
