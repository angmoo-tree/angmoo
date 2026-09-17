"""Bounded World character display names, not private profile material."""

from sqlalchemy import select
from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter


def episode_actor_labels(session, *, scope, actor_ids):
    values = tuple(dict.fromkeys(identifier for identifier in actor_ids if identifier))
    result = {}
    for offset in range(0, len(values), 400):
        result.update(session.execute(select(WorldCharacter.id, Character.name).join(
            Character, Character.id == WorldCharacter.character_id,
        ).where(WorldCharacter.world_id == scope.world_id,
                WorldCharacter.id.in_(values[offset:offset + 400]))).all())
    return result
