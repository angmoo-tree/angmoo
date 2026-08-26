"""SQLAlchemy Character seeds that never own commit or rollback."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.domain.seed import AutonomousCharacterSeedData
from app.domains.characters.infrastructure.sqlalchemy_models import Character


_HANDLE_SEPARATORS = re.compile(r"[^a-z0-9_]+")


def _handle_base(hint: str, character_id: str) -> str:
    normalized = unicodedata.normalize("NFKD", hint).encode("ascii", "ignore").decode()
    base = _HANDLE_SEPARATORS.sub("_", normalized.lower()).strip("_")
    return (base or f"character_{character_id[-12:]}")[:34]


def _available_handle(db: Session, *, hint: str, character_id: str) -> str:
    base = _handle_base(hint, character_id)
    candidate = base
    suffix = 1
    while db.scalar(select(Character.id).where(Character.handle == candidate)):
        suffix += 1
        marker = f"_{suffix}"
        candidate = f"{base[: 40 - len(marker)]}{marker}"
    return candidate


def seed_autonomous_character(
    db: Session, *, data: AutonomousCharacterSeedData
) -> Character:
    character_id = uuid7_string()
    handle = data.planned_handle or _available_handle(
        db, hint=data.handle_hint, character_id=character_id
    )
    if not handle or len(handle) > 40 or db.scalar(
        select(Character.id).where(Character.handle == handle)
    ):
        raise ValueError("character_handle_unavailable")
    character = Character(
        id=character_id,
        owner_id=data.owner_id,
        name=data.display_name,
        handle=handle,
        avatar_url=data.avatar_url,
        banner_url=data.banner_url,
        one_liner=data.one_liner,
        personality=data.personality,
        speech_style=data.speech_style,
        worldview=data.worldview,
        topic_preferences=", ".join(data.topic_preferences),
        safety_rules="\n".join(data.safety_rules),
        status="active",
        moderation_status="active",
        execution_mode="llm",
        promotion_usage_allowed=False,
        persona_summary=data.persona_summary,
    )
    db.add(character)
    db.flush()
    return character


__all__ = ["seed_autonomous_character"]
