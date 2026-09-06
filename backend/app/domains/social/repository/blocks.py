"""World-scoped mutual block query, in the caller Session."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.domains.social.models import feed as models


def world_character_pair_is_blocked(
    db: Session,
    *,
    world_id: str,
    first_world_character_id: str,
    second_world_character_id: str,
) -> bool:
    return db.scalar(
        select(models.WorldCharacterBlock.id).where(
            models.WorldCharacterBlock.world_id == world_id,
            or_(
                (
                    models.WorldCharacterBlock.blocker_world_character_id
                    == first_world_character_id
                )
                & (
                    models.WorldCharacterBlock.blocked_world_character_id
                    == second_world_character_id
                ),
                (
                    models.WorldCharacterBlock.blocker_world_character_id
                    == second_world_character_id
                )
                & (
                    models.WorldCharacterBlock.blocked_world_character_id
                    == first_world_character_id
                ),
            ),
        )
    ) is not None


def write_pair_is_blocked(db: Session, *, world_id: str, actor_id: str, target_id: str) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    (models.WorldCharacterBlock.blocker_world_character_id == actor_id)
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == target_id
                    ),
                    (models.WorldCharacterBlock.blocker_world_character_id == target_id)
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == actor_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )
