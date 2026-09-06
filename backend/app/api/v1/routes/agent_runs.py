from fastapi import APIRouter

from fastapi import Depends

from sqlalchemy.orm import Session

from app import schemas

from app.domains.identity.models import User as _model_User

from app.runtime.persistence.model_registration import register_models

from app.domains.identity.dependencies import get_current_user

from app.database import get_db

from app.domains.routines.service import slot_status as agent_run_service

register_models()

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])

@router.get("/resident-slots", response_model=list[schemas.AgentSlotPublicRead])
def list_resident_slots(
    db: Session = Depends(get_db),
    user: _model_User = Depends(get_current_user),
) -> list[schemas.AgentSlotPublicRead]:
    return agent_run_service.list_resident_slots_for_user(db, user.id)
