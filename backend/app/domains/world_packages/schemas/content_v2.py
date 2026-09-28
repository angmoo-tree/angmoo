"""Version 2 preserves persona text and expands its storage budget.

The version 1 models and published schemas remain frozen.
"""

from typing import Literal
from pydantic import Field, field_validator

from app.domains.characters.contracts import PERSONA_SUMMARY_LIMIT, normalize_persona_text
from app.domains.world_packages.schemas.content import (
    AutonomousCharacterTemplate, CharactersDocument,
)

# Published v2 field set is immutable even when the live Character adds fields.
V2_PERSONA_LIMITS = {
    "one_liner": 500, "personality": 6000, "speech_style": 4000,
    "worldview": 8000, "topic_preferences": 3000, "safety_rules": 4000,
}


class AutonomousCharacterTemplateV2(AutonomousCharacterTemplate):
    one_liner: str = Field(default="", max_length=V2_PERSONA_LIMITS["one_liner"])
    personality: str = Field(default="", max_length=V2_PERSONA_LIMITS["personality"])
    speech_style: str = Field(default="", max_length=V2_PERSONA_LIMITS["speech_style"])
    worldview: str = Field(default="", max_length=V2_PERSONA_LIMITS["worldview"])
    topic_preferences: str = Field(default="", max_length=V2_PERSONA_LIMITS["topic_preferences"])
    safety_rules: str = Field(default="", max_length=V2_PERSONA_LIMITS["safety_rules"])
    persona_summary: str = Field(default="", max_length=PERSONA_SUMMARY_LIMIT)

    @field_validator(*V2_PERSONA_LIMITS, "persona_summary", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return normalize_persona_text(value) if isinstance(value, str) else value


class CharactersDocumentV2(CharactersDocument):
    schema_version: Literal["characters-content-v2"]
    characters: list[AutonomousCharacterTemplateV2] = Field(max_length=50)


def upgrade_character(item: AutonomousCharacterTemplate) -> AutonomousCharacterTemplateV2:
    if isinstance(item, AutonomousCharacterTemplateV2):
        return item
    values = item.model_dump()
    values["topic_preferences"] = ", ".join(item.topic_preferences)
    values["safety_rules"] = "\n".join(item.safety_rules)
    return AutonomousCharacterTemplateV2.model_validate(values)
