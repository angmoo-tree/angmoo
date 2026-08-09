from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ActivityDaypart = Literal["dawn", "morning", "afternoon", "evening"]
ActivityPlanStatus = Literal[
    "planned", "active", "completed", "interrupted", "cancelled"
]
ActivityPlanItemStatus = Literal[
    "planned", "active", "completed", "skipped", "interrupted", "cancelled"
]
ActivityEpisodeStatus = Literal[
    "planned", "active", "completed", "interrupted", "cancelled"
]


class WorldActivityRuntimeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DailyActivityPlanPrepareCreate(WorldActivityRuntimeSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)


class ActivityEpisodeRead(WorldActivityRuntimeSchema):
    id: str
    plan_item_id: str
    status: ActivityEpisodeStatus
    current_state_schema_version: int
    current_state_snapshot: dict[str, object]
    last_successful_beat_id: str | None = None
    last_successful_beat_at: datetime | None = None
    next_sequence_no: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    terminal_reason_code: str | None = None


class DailyActivityPlanItemRead(WorldActivityRuntimeSchema):
    id: str
    daypart: ActivityDaypart
    selected_candidate_id: str
    candidate_signature: str
    candidate_ordinal: int
    activity_kind: str
    title: str
    activity_seed: str
    social_mode: str
    place_key: str | None = None
    joint_activity_id: str | None = None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: ActivityPlanItemStatus
    revision_count: int
    terminal_reason_code: str | None = None
    episode: ActivityEpisodeRead | None = None


class DailyActivityPlanRead(WorldActivityRuntimeSchema):
    id: str
    world_id: str
    world_character_id: str
    local_date: date
    timezone_name: str
    timezone_contract_version: str
    repertoire_id: str
    world_definition_hash: str
    character_definition_hash: str
    repertoire_contract_version: str
    selection_contract_version: str
    selection_seed_hash: str
    status: ActivityPlanStatus
    revision_count: int
    version: int
    autonomous_enabled: bool
    current_daypart: ActivityDaypart | None = None
    reused: bool = False
    items: list[DailyActivityPlanItemRead] = Field(min_length=4, max_length=4)
