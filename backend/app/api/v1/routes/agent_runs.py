from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import agent_runs as agent_run_service
from app.services import community as community_service
from app.services import maintenance as maintenance_service
from app.services.runtime_boundary import OpenClawGatewayAuthError, OpenClawGatewayError

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


def _ensure_same_user(user: models.User, requested_user_id: str | None) -> None:
    if requested_user_id is not None and requested_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot operate on another user's agent run",
        )


@router.get("/resident-slots", response_model=list[schemas.AgentSlotPublicRead])
def list_resident_slots(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.AgentSlotPublicRead]:
    return agent_run_service.list_resident_slots_for_user(db, user.id)


@router.post("/resident-slots/assign", response_model=schemas.AgentSlotRead)
def assign_resident_slot(
    data: schemas.AgentSlotAssignCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentSlotRead:
    _ensure_same_user(user, data.user_id)
    try:
        return agent_run_service.assign_resident_slot(db, data)
    except maintenance_service.AgentActivityMaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except community_service.CharacterNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        ) from exc
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except agent_run_service.CredentialNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        ) from exc
    except agent_run_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_run_service.AgentSlotUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except (
        agent_run_service.CharacterOwnershipError,
        agent_run_service.CredentialOwnershipError,
        agent_run_service.CredentialDisabledError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.post("/community-once", response_model=schemas.OpenClawAgentRunRead)
async def run_community_once(
    data: schemas.OpenClawCommunityRunCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.OpenClawAgentRunRead:
    _ensure_same_user(user, data.user_id)
    data = data.model_copy(update={"user_id": user.id})
    try:
        return await agent_run_service.run_community_once(db, data)
    except maintenance_service.AgentActivityMaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except agent_run_service.OpenClawNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except community_service.PostNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        ) from exc
    except community_service.CharacterNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        ) from exc
    except community_service.CharacterOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except agent_run_service.CredentialNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        ) from exc
    except agent_run_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_run_service.AgentSlotUnavailableError,
        agent_run_service.AgentSessionBusyError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except (
        agent_run_service.CharacterOwnershipError,
        agent_run_service.CredentialOwnershipError,
        agent_run_service.CredentialDisabledError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except agent_run_service.CredentialSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except OpenClawGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
