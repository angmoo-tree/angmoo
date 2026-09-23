"""Owner-only recommendation settings; composition owns foreign source facts."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.social.schemas.recommendation import TopicKeyRequest, TopicRegenerateRequest, RecommendationTopicsRead
from app.domains.identity.service.credential_resolution import CredentialResolutionError
from app.api.recommendation_dependencies import recommendation_workflows
from app.domains.social.contracts.recommendation import TopicPreparationError

router = APIRouter(prefix="/worlds/{world_id}/recommendation-topics", tags=["recommendation-topics"])


def translate_error(exc):
    code = str(exc) if isinstance(exc, TopicPreparationError) else "credential_required"
    status = 403 if code in {"world_not_owned", "character_not_owned"} else 404 if code in {"world_not_available", "character_not_available"} else 422
    raise HTTPException(status_code=status, detail=code) from exc


@router.get("", response_model=RecommendationTopicsRead)
def read(world_id: str, world_character_id: str | None = None, db: Session = Depends(get_db), user=Depends(get_current_user), topics=Depends(recommendation_workflows)):
    try:
        return topics.read_topics(db, world_id=world_id, owner_id=user.id, world_character_id=world_character_id)
    except TopicPreparationError as exc:
        translate_error(exc)


@router.put("/key", response_model=RecommendationTopicsRead)
def connect(world_id: str, data: TopicKeyRequest, db: Session = Depends(get_db), user=Depends(get_current_user), topics=Depends(recommendation_workflows)):
    try:
        return topics.connect_key(db, world_id=world_id, owner_id=user.id, world_character_id=data.world_character_id)
    except TopicPreparationError as exc:
        translate_error(exc)


@router.post("/regenerate", response_model=RecommendationTopicsRead)
async def regenerate(world_id: str, data: TopicRegenerateRequest, world_character_id: str | None = None,
                     db: Session = Depends(get_db), user=Depends(get_current_user), topics=Depends(recommendation_workflows)):
    try:
        return await topics.regenerate(db, world_id=world_id, owner_id=user.id,
            world_character_id=world_character_id, request_id=data.request_id)
    except (TopicPreparationError, CredentialResolutionError) as exc:
        translate_error(exc)
