"""Version 2 preserves persona text and expands its storage budget.

The version 1 models and published schemas remain frozen.
"""

from typing import Literal
from pydantic import Field, field_validator

from app.domains.characters.contracts import (
    PERSONA_LIMITS, PERSONA_SUMMARY_LIMIT, normalize_persona_text,
)
from app.domains.world_packages.schemas.content import (
    AutonomousCharacterTemplate, CharactersDocument,
)


class AutonomousCharacterTemplateV2(AutonomousCharacterTemplate):
    one_liner: str = Field(default="", max_length=PERSONA_LIMITS["one_liner"])
    personality: str = Field(default="", max_length=PERSONA_LIMITS["personality"])
    speech_style: str = Field(default="", max_length=PERSONA_LIMITS["speech_style"])
    worldview: str = Field(default="", max_length=PERSONA_LIMITS["worldview"])
    topic_preferences: str = Field(default="", max_length=PERSONA_LIMITS["topic_preferences"])
    safety_rules: str = Field(default="", max_length=PERSONA_LIMITS["safety_rules"])
    persona_summary: str = Field(default="", max_length=PERSONA_SUMMARY_LIMIT)

    @field_validator(*PERSONA_LIMITS, "persona_summary", mode="before")
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
