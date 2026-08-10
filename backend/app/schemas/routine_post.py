from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RoutineSceneKind = Literal["start", "continue", "conclude"]
RoutineEventEffectKind = Literal[
    "acknowledge",
    "accept_advice",
    "disagree",
    "encouraged",
    "concerned",
]


class RoutinePostSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoutineStateChange(RoutinePostSchema):
    mood: Literal[
        "neutral",
        "curious",
        "joyful",
        "hopeful",
        "calm",
        "concerned",
        "frustrated",
        "sad",
        "embarrassed",
    ] | None = None
    mood_intensity_delta: int = Field(default=0, ge=-20, le=20)
    energy_delta: int = Field(default=0, ge=-20, le=20)
    social_energy_delta: int = Field(default=0, ge=-20, le=20)
    action_note: str | None = Field(default=None, max_length=160)


class RoutineSourceEventEffect(RoutinePostSchema):
    source_event_id: str = Field(min_length=1, max_length=64)
    effect: RoutineEventEffectKind
    intensity: int = Field(ge=0, le=20)
    state_change: RoutineStateChange = Field(default_factory=RoutineStateChange)


class RoutineBeatPlan(RoutinePostSchema):
    episode_id: str = Field(min_length=1, max_length=64)
    beat_id: str = Field(min_length=1, max_length=64)
    sequence_no: int = Field(ge=1)
    scene_kind: RoutineSceneKind
    scene_brief: str = Field(min_length=1, max_length=800)
    continuity_facts: list[str] = Field(default_factory=list, max_length=6)
    considered_source_event_ids: list[str] = Field(default_factory=list, max_length=8)
    used_source_event_ids: list[str] = Field(default_factory=list, max_length=8)
    used_detail_keys: list[str] = Field(default_factory=list, max_length=8)
    source_event_effects: list[RoutineSourceEventEffect] = Field(
        default_factory=list, max_length=8
    )

    @model_validator(mode="after")
    def validate_event_sets(self) -> "RoutineBeatPlan":
        considered = self.considered_source_event_ids
        used = self.used_source_event_ids
        continuity = self.continuity_facts
        details = self.used_detail_keys
        if len(considered) != len(set(considered)) or len(used) != len(set(used)):
            raise ValueError("source event ids must be unique")
        if len(continuity) != len(set(continuity)):
            raise ValueError("continuity facts must be unique")
        if len(details) != len(set(details)):
            raise ValueError("used detail keys must be unique")
        if not set(used).issubset(considered):
            raise ValueError("used source events must be considered")
        effect_ids = [item.source_event_id for item in self.source_event_effects]
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("source event effects must be unique")
        if not set(effect_ids).issubset(used):
            raise ValueError("source event effects must reference used events")
        return self


class RoutinePostDraft(RoutinePostSchema):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    topic_signature: str = Field(min_length=1, max_length=300)
    novelty_basis: str = Field(min_length=1, max_length=500)
