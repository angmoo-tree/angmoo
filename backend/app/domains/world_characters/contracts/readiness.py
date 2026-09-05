"""Fields needed to assess legacy tendency and World readiness without ORM coupling."""
from datetime import datetime
from typing import Any, Protocol
from app.domains.world_characters.contracts.setup import CharacterGenerationRecord


class ReadinessCharacter(CharacterGenerationRecord, Protocol):
    owner_id: str


class ReadinessSetting(Protocol):
    planner_tendency_profile: Any
    tendency_updated_at: datetime | None
    tendency_summary: str
    tendency_action_ranges: Any
