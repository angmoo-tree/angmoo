from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.identity.models import User
from app.domains.worlds.service import foundation as world_foundation
from app.domains.worlds.service.foundation import (
    ANGMOO_GLOBAL_WORLD_ID,
    GlobalFoundationReport,
    stable_backfill_uuid7,
)
from app.domains.world_characters.service import foundation as resident_foundation


def choose_global_owner_user_id(db: Session) -> str | None:
    user_id = db.scalar(
        select(User.id)
        .where(User.deleted_at.is_(None), User.is_admin.is_(True))
        .order_by(User.created_at, User.id)
        .limit(1)
    )
    if user_id is not None:
        return user_id
    user_id = db.scalar(
        select(Character.owner_id)
        .join(User, User.id == Character.owner_id)
        .where(
            Character.deleted_at.is_(None),
            User.deleted_at.is_(None),
        )
        .order_by(Character.created_at, Character.owner_id)
        .limit(1)
    )
    if user_id is not None:
        return user_id
    return db.scalar(
        select(User.id)
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at, User.id)
        .limit(1)
    )


def ensure_angmoo_global_foundation(db: Session) -> GlobalFoundationReport:
    owner_user_id = choose_global_owner_user_id(db)
    if owner_user_id is None:
        return GlobalFoundationReport(False, None, None, 0, 0)

    world = world_foundation.ensure_global_world(db, owner_user_id=owner_user_id)

    now = datetime.now(timezone.utc)
    owner_ids = list(
        db.scalars(
            select(Character.owner_id)
            .join(User, User.id == Character.owner_id)
            .where(
                Character.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .distinct()
            .order_by(Character.owner_id)
        )
    )
    if owner_user_id not in owner_ids:
        owner_ids.insert(0, owner_user_id)

    membership_by_user = world_foundation.ensure_global_memberships(
        db, world=world, owner_user_id=owner_user_id, owner_ids=owner_ids, now=now
    )

    characters = list(
        db.scalars(
            select(Character)
            .where(Character.deleted_at.is_(None))
            .order_by(Character.id)
        )
    )
    for character in characters:
        existing = resident_foundation.find_global_world_character(
            db, world_id=world.id, character_id=character.id
        )
        if existing is None:
            resident_foundation.add_global_world_character(
                db,
                identifier=stable_backfill_uuid7(
                    "angmoo-global-world-character", character.id
                ),
                world_id=world.id,
                character_id=character.id,
                membership_id=membership_by_user[character.owner_id].id,
                world_contract_hash=world.contract_hash,
            )
    db.flush()
    membership_count = world_foundation.count_global_memberships(db, world_id=world.id)
    world_character_count = resident_foundation.count_global_world_characters(
        db, world_id=world.id
    )
    return GlobalFoundationReport(
        True,
        world.id,
        owner_user_id,
        membership_count,
        world_character_count,
    )
