"""Active-participant, block, place, daypart and role admission for joint opening."""
from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from app.domains.routines.contracts.joint_activity import JointReferences
from app.domains.routines.exceptions import JointActivityRuntimeError
from app.domains.routines.constants import DAYPARTS


def _eligible_world_character(
    db: Session, *, references: JointReferences, world_id: str, world_character_id: str
) -> Any:
    world_character = references.get_world_character(world_character_id)
    if (
        world_character is None
        or world_character.world_id != world_id
        or world_character.status != "active"
    ):
        raise JointActivityRuntimeError("world_character_ineligible")
    membership = references.get_membership(world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.status != "active"
    ):
        raise JointActivityRuntimeError("world_membership_inactive")
    return world_character



def validate_pair(
    db: Session,
    *,
    references: JointReferences,
    world_id: str,
    first_world_character_id: str,
    second_world_character_id: str,
) -> tuple[Any, Any]:
    if first_world_character_id == second_world_character_id:
        raise JointActivityRuntimeError("self_target_forbidden")
    first = _eligible_world_character(
        db, references=references, world_id=world_id, world_character_id=first_world_character_id
    )
    second = _eligible_world_character(
        db, references=references, world_id=world_id, world_character_id=second_world_character_id
    )
    if references.mutually_blocked(
        world_id=world_id,
        first_id=first_world_character_id,
        second_id=second_world_character_id,
    ):
        raise JointActivityRuntimeError("world_character_blocked")
    return first, second



def validate_place(
    db: Session,
    *,
    references: JointReferences,
    world_id: str,
    place_key: str | None,
    target_daypart: str,
    participant_role_keys: tuple[str | None, str | None],
) -> None:
    if target_daypart not in DAYPARTS:
        raise JointActivityRuntimeError("daypart_invalid")
    if place_key is None:
        return
    place = references.get_enabled_place(world_id=world_id, place_key=place_key)
    if place is None:
        raise JointActivityRuntimeError("world_place_invalid")
    if place.available_dayparts and target_daypart not in place.available_dayparts:
        raise JointActivityRuntimeError("world_place_daypart_invalid")
    if place.access_role_keys and any(
        role_key not in place.access_role_keys for role_key in participant_role_keys
    ):
        raise JointActivityRuntimeError("world_place_role_forbidden")
