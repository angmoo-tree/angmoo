"""SQLAlchemy WorldCharacter seeds that never own commit or rollback."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.world_characters.domain.runtime_modes import (
    AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
    AUTONOMOUS_FEED_RUNTIME_MODE,
)
from app.domains.world_characters.domain.seed import (
    AutonomousWorldCharacterSeedData,
)
from app.domains.world_characters.infrastructure.sqlalchemy_models import WorldCharacter


def seed_autonomous_world_character(
    db: Session, *, data: AutonomousWorldCharacterSeedData
) -> WorldCharacter:
    world_character = WorldCharacter(
        id=uuid7_string(),
        world_id=data.world_id,
        character_id=data.character_id,
        membership_id=data.membership_id,
        role_key=data.role_key,
        status="pending",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=False,
        activity_runtime_mode=AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
        feed_runtime_mode=AUTONOMOUS_FEED_RUNTIME_MODE,
        local_profile={
            "role_description": data.role_description,
            "background": data.background,
            "access_scope": list(data.access_scope),
        },
        version=1,
    )
    db.add(world_character)
    db.flush()
    return world_character


__all__ = ["seed_autonomous_world_character"]
