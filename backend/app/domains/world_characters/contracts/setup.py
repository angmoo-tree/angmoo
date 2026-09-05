"""Provider-free values used by WorldCharacter generation validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.world_characters.schemas import setup as schemas


class CharacterGenerationRecord(Protocol):
    id: str | None
    name: str | None
    one_liner: str | None
    personality: str | None
    speech_style: str | None
    worldview: str | None
    topic_preferences: str | None
    safety_rules: str | None
    persona_summary: str | None


@dataclass(frozen=True)
class ValidatedActivityCandidate:
    payload: schemas.WorldActivityCandidatePayload
    ordinal: int
    canonical_signature: str

@dataclass(frozen=True)
class ValidatedActivityRepertoire:
    candidates: tuple[ValidatedActivityCandidate, ...]
    daypart_counts: dict[str, int]
    near_duplicate_pair_count: int
