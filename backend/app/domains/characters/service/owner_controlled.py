"""Character writes participating in owner-controlled identity transactions.

The caller validates World and installation ownership and owns commit/rollback.
These operations return or modify the same session-attached Character object.
"""
from __future__ import annotations

from collections.abc import Sequence
from sqlalchemy.orm import Session
from app.domains.characters.models import Character


def seed_owner_controlled_character(
    db: Session, *, character_id: str, owner_id: str, display_name: str,
    avatar_url: str | None, intro: str, interests: Sequence[str], background: str,
) -> Character:
    character = Character(
        id=character_id, owner_id=owner_id, name=display_name,
        handle=f"owner-{character_id[-20:]}", avatar_url=avatar_url,
        banner_url=None, one_liner=intro, personality="", speech_style="",
        worldview="", topic_preferences=", ".join(interests), safety_rules="",
        status="active", execution_mode="local", promotion_usage_allowed=False,
        persona_summary=background or intro,
    )
    db.add(character)
    db.flush()
    return character


def update_owner_controlled_character(
    character: Character, *, display_name: str, avatar_url: str | None,
    intro: str, interests: Sequence[str], background: str,
) -> None:
    """Modify the attached identity without introducing flush or commit."""
    character.name = display_name
    character.avatar_url = avatar_url
    character.one_liner = intro
    character.topic_preferences = ", ".join(interests)
    character.persona_summary = background or intro
