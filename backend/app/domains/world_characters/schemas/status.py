from typing import Literal
from pydantic import BaseModel, Field
from app.domains.world_characters.schemas.management import DashboardStatus


class StatusActivity(BaseModel):
    id: str
    action: str
    status: str
    occurred_at: str
    post_id: str | None = None
    title: str | None = None


class WorldCharacterStatusRead(BaseModel):
    contract_version: Literal["world-character-status-v1"] = "world-character-status-v1"
    world_id: str
    world_character_id: str
    revision: int
    autonomous_enabled: bool
    state: DashboardStatus
    timezone: str
    next_activity_at: str | None
    recent_activity: list[StatusActivity] = Field(max_length=20)
    persona: dict[str, str]
    summary: dict[str, int | str | list[str] | None]
