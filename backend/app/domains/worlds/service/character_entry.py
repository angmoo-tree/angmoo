"""World records used by Character entry in the caller transaction.

These are bounded entry lookups/writes. They never export ORM classes, commit,
refresh unrelated rows, or replace the caller's WC error/status decisions.
"""
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.worlds import models
from app.domains.worlds.service.definition import refresh_world_contract


def get_character_entry_world(db: Session, world_id: str):
    return db.get(models.World, world_id)


def get_character_entry_membership(db: Session, membership_id: str):
    return db.get(models.WorldMembership, membership_id)


def find_character_entry_membership(db: Session, *, world_id: str, user_id: str):
    return db.scalar(select(models.WorldMembership).where(
        models.WorldMembership.world_id == world_id,
        models.WorldMembership.user_id == user_id,
    ))


def seed_open_character_membership(db: Session, *, world_id: str, user_id: str):
    """Caller has already checked the absent membership and open join policy."""
    membership = models.WorldMembership(
        id=uuid7_string(), world_id=world_id, user_id=user_id,
        role="member", status="active", requested_by_user_id=user_id,
        approved_by_user_id=user_id, joined_at=datetime.now(UTC),
    )
    db.add(membership)
    db.flush()
    return membership


def list_autonomous_entry_roles(db: Session, *, world_id: str):
    return list(db.scalars(select(models.WorldRole).where(
        models.WorldRole.world_id == world_id,
        models.WorldRole.status == "enabled",
        models.WorldRole.autonomous_allowed.is_(True),
    )))


def find_autonomous_entry_role(db: Session, *, world_id: str, role_key: str | None):
    return db.scalar(select(models.WorldRole).where(
        models.WorldRole.world_id == world_id,
        models.WorldRole.role_key == role_key,
        models.WorldRole.status == "enabled",
        models.WorldRole.autonomous_allowed.is_(True),
    ))


def refresh_entry_world_contract(db: Session, world) -> None:
    """Retain conditional version increments; caller retains its original flush."""
    if refresh_world_contract(db, world):
        world.definition_version += 1
        world.row_version += 1
