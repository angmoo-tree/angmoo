"""Owner HTTP for LocalBot key management under the existing Agent URL."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.domains.local_bot import schemas
from app.domains.local_bot.contracts.key_management import LocalKeyOwner, LocalKeyWorkflows
from app.domains.local_bot.dependencies import get_current_user, get_db, get_local_key_workflows
from app.domains.local_bot.service import key_management
from app.domains.characters.service.access import AgentNotFoundError, AgentExecutionModeError

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get('/{character_id}/local-connection', response_model=schemas.AgentLocalConnectionRead)
def get_local_connection(character_id: str, db: Session=Depends(get_db), user: LocalKeyOwner=Depends(get_current_user)) -> schemas.AgentLocalConnectionRead:
    try:
        return key_management.get_local_connection(db, user, character_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Agent not found') from exc
    except AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post('/{character_id}/local-key', response_model=schemas.AgentLocalKeyCreateRead, status_code=status.HTTP_201_CREATED)
def issue_local_key(character_id: str, db: Session=Depends(get_db), user: LocalKeyOwner=Depends(get_current_user), workflows: LocalKeyWorkflows=Depends(get_local_key_workflows)) -> schemas.AgentLocalKeyCreateRead:
    try:
        return key_management.issue_local_key(db, user, character_id, workflows=workflows)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Agent not found') from exc
    except AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete('/{character_id}/local-key', status_code=status.HTTP_204_NO_CONTENT)
def revoke_local_key(character_id: str, db: Session=Depends(get_db), user: LocalKeyOwner=Depends(get_current_user), workflows: LocalKeyWorkflows=Depends(get_local_key_workflows)) -> Response:
    try:
        key_management.revoke_local_key(db, user, character_id, workflows=workflows)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Agent not found') from exc
    except AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
