"""One coherent current state, distinct from an activity's recorded thought."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mood = Literal["neutral", "curious", "joyful", "hopeful", "calm", "concerned", "frustrated", "sad", "embarrassed"]
ActivityEngine = Literal["current", "personalized_graph_v2"]


class StateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mood: Mood
    mood_intensity: int = Field(ge=0, le=100)
    state_note: str = Field(min_length=1, max_length=160)


class EngineSelection(BaseModel):
    engine: ActivityEngine | None  # null removes the explicit override
    expected_version: int = Field(ge=0)
