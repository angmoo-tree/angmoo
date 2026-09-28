"""World Package v3 adds independent optional character background."""

from typing import Literal

from pydantic import Field, field_validator

from app.domains.characters.contracts import normalize_persona_text
from app.domains.world_packages.schemas.content_v2 import (
    AutonomousCharacterTemplateV2, CharactersDocumentV2, upgrade_character,
)


class AutonomousCharacterTemplateV3(AutonomousCharacterTemplateV2):
    character_background: str = Field(default="", max_length=8000)

    @field_validator("character_background", mode="before")
    @classmethod
    def normalize_background(cls, value):
        return normalize_persona_text(value) if isinstance(value, str) else value


class CharactersDocumentV3(CharactersDocumentV2):
    schema_version: Literal["characters-content-v3"]
    characters: list[AutonomousCharacterTemplateV3] = Field(max_length=50)


def upgrade_character_v3(item) -> AutonomousCharacterTemplateV3:
    if isinstance(item, AutonomousCharacterTemplateV3):
        return item
    upgraded = upgrade_character(item)
    return AutonomousCharacterTemplateV3.model_validate({
        **upgraded.model_dump(),
        "character_background": getattr(item, "character_background", ""),
    })
