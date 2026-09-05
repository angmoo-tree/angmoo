"""Original Character/World membership/block joins in the Memory read Session."""
from sqlalchemy import select
from app.domains.characters.models import Character
from app.runtime.memory.sqlalchemy_source_reader import models as source_models


def read_character_summary_rows(session, query, requested):
    rows = list(
        session.execute(
            select(source_models.WorldCharacter, Character)
            .join(
                Character,
                Character.id == source_models.WorldCharacter.character_id,
            )
            .join(
                source_models.WorldMembership,
                source_models.WorldMembership.id
                == source_models.WorldCharacter.membership_id,
            )
            .where(
                source_models.WorldCharacter.id.in_(requested),
                source_models.WorldCharacter.world_id == query.scope.world_id,
                source_models.WorldCharacter.status == "active",
                source_models.WorldMembership.status == "active",
            )
            .order_by(source_models.WorldCharacter.id)
            .limit(query.limit)
        )
    )
    blocked = set(
        session.scalars(
            select(source_models.WorldCharacterBlock.blocked_world_character_id).where(
                source_models.WorldCharacterBlock.world_id == query.scope.world_id,
                source_models.WorldCharacterBlock.blocker_world_character_id
                == query.scope.subject_world_character_id,
            )
        )
    ) | set(
        session.scalars(
            select(source_models.WorldCharacterBlock.blocker_world_character_id).where(
                source_models.WorldCharacterBlock.world_id == query.scope.world_id,
                source_models.WorldCharacterBlock.blocked_world_character_id
                == query.scope.subject_world_character_id,
            )
        )
    )
    return rows, blocked
