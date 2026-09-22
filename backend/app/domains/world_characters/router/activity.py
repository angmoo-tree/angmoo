"""Local owner controls separate engine policy from autonomous ON/OFF."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.identity_dependencies import get_current_user, browser_session
from app.database import get_db
from app.domains.identity.service.local_owner import LocalIdentityService
from app.domains.world_characters.schemas.activity_state import ActivityEngine
from app.domains.world_characters.service.activity_engines import set_engine
from app.domains.world_characters.service.activity_status import owned_actor, activity_status

router = APIRouter(prefix="/worlds", tags=["world-character-activity"])


class EngineWrite(BaseModel):
    scope: Literal["character", "world", "global"]
    engine: ActivityEngine | None
    expected_version: int = Field(ge=0)


def _owner_actor(db, request, user, world_id, actor_id, *, mutation):
    browser_session.require_local_frontend_request(request, mutation=mutation)
    owner = LocalIdentityService(db).get_bootstrap_status().owner
    if owner is None or owner.user_id != user.id:
        raise HTTPException(403, "local_owner_required")
    try:
        return owned_actor(db, actor_id=actor_id, world_id=world_id, owner_id=user.id, read_character=request.app.state.activity_character_reader)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/{world_id}/world-characters/{actor_id}/activity-runtime")
def read_activity_runtime(world_id: str, actor_id: str, request: Request,
                          db: Session = Depends(get_db), user=Depends(get_current_user)):
    actor = _owner_actor(db, request, user, world_id, actor_id, mutation=False)
    return activity_status(db, actor=actor)


@router.put("/{world_id}/world-characters/{actor_id}/activity-runtime")
def update_activity_runtime(world_id: str, actor_id: str, data: EngineWrite, request: Request,
                            db: Session = Depends(get_db), user=Depends(get_current_user)):
    actor = _owner_actor(db, request, user, world_id, actor_id, mutation=True)
    try:
        set_engine(db, engine=data.engine, expected_version=data.expected_version,
            world_id=world_id if data.scope != "global" else None,
            actor_id=actor_id if data.scope == "character" else None)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409 if "conflict" in str(exc) else 422, str(exc)) from exc
    return activity_status(db, actor=actor)
