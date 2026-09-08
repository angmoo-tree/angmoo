"""Read the execution pair independently of pending generation results."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.world_characters import models


def get_approved_pair(
    db: Session, world_character_id: str,
) -> tuple[models.WorldCommunityProfile, models.WorldActivityRepertoire] | None:
    row = db.execute(
        select(models.WorldCommunityProfile, models.WorldActivityRepertoire)
        .join(
            models.WorldActivityRepertoire,
            models.WorldActivityRepertoire.community_profile_id == models.WorldCommunityProfile.id,
        )
        .where(
            models.WorldCommunityProfile.world_character_id == world_character_id,
            models.WorldActivityRepertoire.world_character_id == world_character_id,
            models.WorldCommunityProfile.status == "ready",
            models.WorldActivityRepertoire.status == "ready",
        )
        .order_by(
            models.WorldActivityRepertoire.approved_at.desc(),
            models.WorldActivityRepertoire.generated_at.desc(),
            models.WorldActivityRepertoire.id.desc(),
        )
        .limit(1)
    ).first()
    return (row[0], row[1]) if row is not None else None
