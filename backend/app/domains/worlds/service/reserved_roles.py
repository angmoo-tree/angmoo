"""Idempotent persistence helpers for system-owned World roles."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.worlds.contracts import (
    NO_SPECIFIC_ROLE_DESCRIPTION,
    NO_SPECIFIC_ROLE_KEY,
    NO_SPECIFIC_ROLE_NAME,
    is_canonical_no_specific_role,
)
from app.domains.worlds import models
from app.domains.worlds.exceptions import ReservedWorldRoleConflictError


def ensure_no_specific_role(db: Session, *, world_id: str) -> models.WorldRole:
    role = db.scalar(
        select(models.WorldRole)
        .where(
            models.WorldRole.world_id == world_id,
            models.WorldRole.role_key == NO_SPECIFIC_ROLE_KEY,
        )
        .with_for_update()
    )
    if role is None:
        role = models.WorldRole(
            id=uuid7_string(),
            world_id=world_id,
            role_key=NO_SPECIFIC_ROLE_KEY,
            version=1,
            name=NO_SPECIFIC_ROLE_NAME,
            description=NO_SPECIFIC_ROLE_DESCRIPTION,
            responsibilities=[],
            allowed_activity_scope=[],
            autonomous_allowed=True,
            status="enabled",
        )
        db.add(role)
        db.flush()
        return role
    if not is_canonical_no_specific_role(role):
        raise ReservedWorldRoleConflictError("reserved_world_role_conflict")
    if role.status != "enabled":
        role.status = "enabled"
        role.version += 1
        db.flush()
    return role


__all__ = ["ReservedWorldRoleConflictError", "ensure_no_specific_role"]
