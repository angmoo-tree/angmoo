"""Exact model compatibility for the immutable SQLite v2->v3 migration."""

from app.domains.world_characters.models import (
    JSON_DOCUMENT,
    WorldCharacter,
    CharacterActiveWorld,
)

__all__ = ['JSON_DOCUMENT', 'WorldCharacter', 'CharacterActiveWorld']
