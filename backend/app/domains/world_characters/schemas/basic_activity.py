"""The optional activity step exposes saved policy, never a full persona or secret."""
from typing import Literal
from pydantic import BaseModel
from app.domains.world_characters.schemas.management import ExpectedWorldRevision, WorldEditableSettings


class BasicActivityPolicy(BaseModel):
    active_hours_start: str
    active_hours_end: str
    activity_interval_minutes: int
    max_posts_per_day: int
    max_comments_per_day: int
    allow_post: bool
    allow_reply: bool
    allow_like: bool


class BasicActivitySettingsRead(BaseModel):
    contract_version: Literal["world-activity-settings-v1"] = "world-activity-settings-v1"
    world_id: str
    world_character_id: str
    character_id: str
    revision: int
    timezone: str
    autonomous_enabled: bool
    policy: BasicActivityPolicy
    can_activate: bool
    can_deactivate: bool
    reason: str | None


class BasicActivitySettingsPatch(ExpectedWorldRevision):
    active_hours_start: str | None = None
    active_hours_end: str | None = None
    activity_interval_minutes: int | None = None
    max_posts_per_day: int | None = None
    max_comments_per_day: int | None = None
    allow_post: bool | None = None
    allow_reply: bool | None = None
    allow_like: bool | None = None

    def editable_policy(self):
        # Delegate field and time validation to the existing settings contract.
        return WorldEditableSettings.model_validate(self.model_dump(exclude_unset=True, exclude={"expected_revision"}))
