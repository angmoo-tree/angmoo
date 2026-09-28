"""Validated daily preparation outputs; dates and identities remain server owned."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.routines.schemas.plans import ActivityDaypart
class InitialTopicDefinition(BaseModel):
    """Initial preparation transport; social service validates canonical identity."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    scope: Literal["common", "world"]



class DailyGenerationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    daypart: ActivityDaypart
    activity_kind: Literal["duty", "rest", "self_care", "hobby", "exploration", "social", "maintenance", "challenge", "joint_activity"]
    title: str = Field(min_length=1, max_length=120)
    activity_seed: str = Field(min_length=1, max_length=500)
    social_mode: Literal["solo", "open_to_interaction", "cooperative", "joint"]
    place_key: str | None = Field(default=None, min_length=1, max_length=64)


class GeneratedDailyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DailyGenerationItem] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def unique_dayparts(self):
        if {item.daypart for item in self.items} != {"dawn", "morning", "afternoon", "evening"}:
            raise ValueError("daily_plan_dayparts_invalid")
        return self


class DailyPreparationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_plan: GeneratedDailyPlan


class InitialPreparationOutput(DailyPreparationOutput):
    recommendation_topics: list[InitialTopicDefinition] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def distinct_topics(self):
        import unicodedata
        keys = [(topic.scope, "".join(unicodedata.normalize("NFKC", topic.name).casefold().split()))
                for topic in self.recommendation_topics]
        if any(len(name) < 2 for _, name in keys) or len(set(keys)) != len(keys):
            raise ValueError("daily_preparation_topics_invalid")
        return self


class DailyPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    expected_version: int | None = Field(default=None, ge=1)


class DailyPreparationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_character_id: str
    local_date: str
    plan_state: Literal["pending", "running", "waiting", "ready", "failed", "needs_user_action"]
    topic_state: Literal["pending", "ready", "needs_user_action"]
    request_id: str | None = None
    attempt_count: int = 0
    reason_code: str | None = None
    plan_id: str | None = None
    next_retry_at: str | None = None
    plan_version: int | None = None
    request_state: str | None = None
    request_reason_code: str | None = None
