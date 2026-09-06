"""Canonical interaction's exact mutual-block query in the caller Session."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.domains.social.models import feed as models


def _blocked(db: Session, *, world_id: str, first_id: str, second_id: str) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    (models.WorldCharacterBlock.blocker_world_character_id == first_id)
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == second_id
                    ),
                    (models.WorldCharacterBlock.blocker_world_character_id == second_id)
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == first_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )
