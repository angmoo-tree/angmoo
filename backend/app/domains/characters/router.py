"""Owner-facing Character HTTP endpoints; mixed activity/media routes stay in API assembly."""
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.domains.characters import schemas, exceptions as errors
from app.domains.characters.contracts import CharacterOwner, CharacterManagementWorkflows, CreatorWorkflows
from app.domains.characters.dependencies import get_current_user, get_db, get_character_management_workflows, get_creator_workflows
from app.domains.characters.service import management as character_service
from app.domains.characters.service import drafts as draft_lifecycle
from app.domains.characters.service import state as character_state
from app.domains.characters.service import creator as creator_policy
from app.domains.runtime.contracts import (
    AgentSlotUnavailableError, OpenClawGatewayError, OpenClawGatewayAuthError,
)
from app.domains.media.contracts import InvalidProfileMediaError as MediaValidationError
from app.domains.identity.service.demo_access import DemoAccountLockedError

router = APIRouter(prefix="/agents", tags=["agents"])


def _raise_demo_account_locked(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("", response_model=list[schemas.AgentDetailRead])
def list_agents(
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CharacterManagementWorkflows = Depends(get_character_management_workflows),
) -> list[schemas.AgentDetailRead]:
    return character_service.list_agents(db, user, workflows=workflows)


@router.post("", response_model=schemas.AgentDetailRead, status_code=status.HTTP_201_CREATED)
def create_agent(
    data: schemas.AgentCreate,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CharacterManagementWorkflows = Depends(get_character_management_workflows),
) -> schemas.AgentDetailRead:
    try:
        return character_service.create_agent(db, user, data, workflows=workflows)
    except errors.AgentHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except errors.AgentHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.AgentActiveHoursInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{character_id}", response_model=schemas.AgentDetailRead)
def get_agent(
    character_id: str,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CharacterManagementWorkflows = Depends(get_character_management_workflows),
) -> schemas.AgentDetailRead:
    try:
        return character_service.get_agent(db, user, character_id, workflows=workflows)
    except errors.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.put("/{character_id}/profile", response_model=schemas.AgentDetailRead)
def update_profile(
    character_id: str,
    data: schemas.AgentProfileUpdate,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CharacterManagementWorkflows = Depends(get_character_management_workflows),
) -> schemas.AgentDetailRead:
    try:
        return character_service.update_profile(db, user, character_id, data, workflows=workflows)
    except errors.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except errors.AgentProfileNameInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.AgentHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except errors.AgentHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{character_id}/persona", response_model=schemas.AgentDetailRead)
def update_persona(
    character_id: str,
    data: schemas.AgentPersonaUpdate,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CharacterManagementWorkflows = Depends(get_character_management_workflows),
) -> schemas.AgentDetailRead:
    try:
        return character_service.update_persona(db, user, character_id, data, workflows=workflows)
    except errors.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except errors.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{character_id}/promotion-usage", response_model=schemas.AgentDetailRead)
def update_promotion_usage(
    character_id: str,
    data: schemas.AgentPromotionUsageUpdate,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CharacterManagementWorkflows = Depends(get_character_management_workflows),
) -> schemas.AgentDetailRead:
    try:
        return character_service.update_promotion_usage(db, user, character_id, data, workflows=workflows)
    except errors.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)


@router.get("/drafts/{draft_id}", response_model=schemas.AgentCreationDraftRead)
def get_agent_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CreatorWorkflows = Depends(get_creator_workflows),
) -> schemas.AgentCreationDraftRead:
    try:
        return draft_lifecycle.get_draft(db, user, draft_id, workflows=workflows)
    except errors.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc


@router.patch("/drafts/{draft_id}", response_model=schemas.AgentCreationDraftRead)
def update_agent_draft(
    draft_id: str,
    data: schemas.AgentCreationDraftUpdate,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CreatorWorkflows = Depends(get_creator_workflows),
) -> schemas.AgentCreationDraftRead:
    try:
        return draft_lifecycle.update_draft(db, user, draft_id, data, workflows=workflows)
    except errors.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except errors.AgentCreationDraftHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except errors.AgentCreationDraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/drafts",
    response_model=schemas.AgentCreationDraftRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_draft(
    data: schemas.AgentCreationDraftCreate,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CreatorWorkflows = Depends(get_creator_workflows),
) -> schemas.AgentCreationDraftRead:
    try:
        return await draft_lifecycle.create_draft(db, user, data, workflows=workflows)
    except errors.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AgentSlotUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except OpenClawGatewayError as exc:
        credential_error = creator_policy.llm_credential_error_message(exc)
        if credential_error is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=credential_error) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/drafts/{draft_id}/enhance-persona",
    response_model=schemas.AgentCreationDraftRead,
)
async def enhance_agent_draft_persona(
    draft_id: str,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CreatorWorkflows = Depends(get_creator_workflows),
) -> schemas.AgentCreationDraftRead:
    try:
        return await draft_lifecycle.enhance_persona(db, user, draft_id, workflows=workflows)
    except errors.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except errors.AgentCreationDraftCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"페르소나 보강은 {exc.available_at.isoformat()} 이후 다시 시도할 수 있습니다.",
        ) from exc
    except errors.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except errors.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AgentSlotUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except errors.AgentCreationDraftParseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except errors.AgentCreationDraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except OpenClawGatewayError as exc:
        credential_error = creator_policy.llm_credential_error_message(exc)
        if credential_error is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=credential_error) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/complete", response_model=schemas.AgentDetailRead)
def complete_agent_draft(
    draft_id: str,
    data: schemas.AgentCreationDraftComplete | None = Body(default=None),
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
    workflows: CreatorWorkflows = Depends(get_creator_workflows),
) -> schemas.AgentDetailRead:
    try:
        return draft_lifecycle.complete_draft(
            db, user, draft_id, data or schemas.AgentCreationDraftComplete(),
            workflows=workflows
        )
    except errors.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except errors.AgentCreationDraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.AgentHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except errors.AgentHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.AgentActiveHoursInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except errors.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MediaValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# The historical state URL belongs to the community HTTP namespace.
state_router = APIRouter(tags=["community"])


@state_router.post(
    "/characters/{character_id}/state", response_model=schemas.CharacterStateRead
)
def save_character_state(
    character_id: str,
    data: schemas.CharacterStateWrite,
    db: Session = Depends(get_db),
    user: CharacterOwner = Depends(get_current_user),
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state_for_user(
            db, user, character_id, data
        )
    except errors.CharacterStateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Character not found"
        )
