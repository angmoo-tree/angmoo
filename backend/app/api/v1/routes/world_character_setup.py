from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.identity.dependencies import get_current_user
from app.core.db import get_db
from app.services import world_feed_search


router = APIRouter(prefix="/world-characters", tags=["world-character-setup"])


@router.get(
    "/{world_character_id}/feed-status",
    response_model=schemas.WorldFeedCycleStatusRead,
)
def get_world_feed_status(
    world_character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldFeedCycleStatusRead:
    try:
        return world_feed_search.owner_world_feed_cycle_status(
            db,
            world_character_id=world_character_id,
            user=user,
        )
    except world_feed_search.WorldFeedStatusNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="world_character_not_found",
        ) from exc
    except world_feed_search.WorldFeedStatusForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="world_character_forbidden",
        ) from exc
