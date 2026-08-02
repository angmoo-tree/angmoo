from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import agent_runs as agent_run_service

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get("/resident-slots", response_model=list[schemas.AgentSlotPublicRead])
def list_resident_slots(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.AgentSlotPublicRead]:
    return agent_run_service.list_resident_slots_for_user(db, user.id)
