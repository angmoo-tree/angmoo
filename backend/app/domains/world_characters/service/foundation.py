from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.world_characters.models import WorldCharacter


def find_global_world_character(
    db: Session, *, world_id: str, character_id: str
) -> str | None:
    return db.scalar(
        select(WorldCharacter.id).where(
            WorldCharacter.world_id == world_id,
            WorldCharacter.character_id == character_id,
        )
    )


def add_global_world_character(
    db: Session,
    *,
    identifier: str,
    world_id: str,
    character_id: str,
    membership_id: str,
    world_contract_hash: str,
) -> None:
    db.add(
        WorldCharacter(
            id=identifier,
            world_id=world_id,
            character_id=character_id,
            membership_id=membership_id,
            status="inactive",
            autonomous_enabled=False,
            character_contract_hash=None,
            world_contract_hash=world_contract_hash,
            version=1,
        )
    )


def count_global_world_characters(db: Session, *, world_id: str) -> int:
    return db.query(WorldCharacter).filter_by(world_id=world_id).count()
