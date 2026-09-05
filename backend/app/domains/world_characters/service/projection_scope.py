"""Historical projection membership checks; active-author admission is separate."""
from sqlalchemy.orm import Session
from app.domains.world_characters import models
from app.domains.world_characters.exceptions import WorldCharacterContractError
from app.domains.worlds.service.character_entry import get_character_entry_membership


def get_projection_world_character(
    db: Session, *, world_id: str, world_character_id: str
) -> models.WorldCharacter:
    row = db.get(models.WorldCharacter, world_character_id)
    if row is None or row.world_id != world_id:
        raise WorldCharacterContractError("world_mismatch")
    membership = get_character_entry_membership(db, row.membership_id)
    if membership is None or membership.world_id != world_id:
        raise WorldCharacterContractError("world_mismatch")
    return row
