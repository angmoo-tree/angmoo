"""WorldCharacter and membership admission for canonical event writes."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.world_characters import models
from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError
from app.domains.worlds.service.character_entry import get_character_entry_membership


def validate_event_scope(
    db: Session,
    *,
    world_id: str,
    world_character_id: str,
    lock: bool = False,
) -> models.WorldCharacter:
    statement = select(models.WorldCharacter).where(
        models.WorldCharacter.id == world_character_id
    )
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None or row.world_id != world_id:
        raise WorldCharacterSocialScopeError("cross_world_reference")
    if row.status != "active":
        raise WorldCharacterSocialScopeError("world_character_inactive")
    membership = get_character_entry_membership(db, row.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.status != "active"
    ):
        raise WorldCharacterSocialScopeError("world_membership_inactive")
    return row
