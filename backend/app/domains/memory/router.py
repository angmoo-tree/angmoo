"""Owner-only Memory HTTP endpoints and stable error translation."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.identity_dependencies import browser_session
from app.domains.memory.contracts.management import MemoryOwner as User, MemoryWorkflows
from app.domains.memory.dependencies import get_current_user, get_db, get_memory_workflows
from app.domains.memory.service import management as memory_service
from app.domains.memory.schemas import (
    MemoryCorrectionCreate,
    MemoryDeleteCreate,
    MemoryEvidenceRead,
    MemoryItemDetailRead,
    MemoryItemListRead,
    MemoryItemMutationRead,
    MemoryItemSummaryRead,
    MemoryPinUpdate,
    MemoryRelatedCharacterRead,
    MemoryScopeRead,
    MemorySettingMutationRead,
    MemorySettingRead,
    MemorySettingUpdate,
)
from app.domains.memory.exceptions import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryScopeError,
    MemoryValidationError,
)
from app.domains.memory.contracts.provenance import MemoryProviderMode, MemorySourceTypeV1
from app.domains.memory.policies.retention import DEFAULT_MEMORY_RETENTION_DAYS
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.schemas.batch import (
    MemoryBatchRetry,
    MemoryBatchSettingRead,
    MemoryBatchSettingUpdate,
)

router = APIRouter(prefix="/worlds/{world_id}/world-characters/{subject_id}", tags=["memory"])


def _scope(user: User, world_id: str, subject_id: str) -> MemoryScope:
    return MemoryScope(
        owner_id=user.id,
        world_id=world_id,
        subject_world_character_id=subject_id,
    )



def _raise_memory_read_error(exc: Exception) -> None:
    if isinstance(exc, MemoryNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryScopeError):
        # The URL never accepts an owner id.  Invalid owner/World/subject
        # combinations are therefore indistinguishable from missing resources.
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryValidationError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = (
        "memory_service_unavailable"
        if code == status.HTTP_503_SERVICE_UNAVAILABLE
        else str(exc)
    )
    raise HTTPException(status_code=code, detail=detail) from None



def _raise_memory_mutation_error(exc: Exception) -> None:
    if isinstance(exc, MemoryNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryScopeError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, MemoryValidationError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = (
        "memory_service_unavailable"
        if code == status.HTTP_503_SERVICE_UNAVAILABLE
        else str(exc)
    )
    raise HTTPException(status_code=code, detail=detail) from None



@router.get("/memory/batch-settings", response_model=MemoryBatchSettingRead)
def read_memory_batch_setting(
    world_id: str,
    subject_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryBatchSettingRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return memory_service.read_memory_batch_setting(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows)
    except Exception as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")



@router.put("/memory/batch-settings", response_model=MemoryBatchSettingRead)
def update_memory_batch_setting(
    world_id: str,
    subject_id: str,
    data: MemoryBatchSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryBatchSettingRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return memory_service.update_memory_batch_setting(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, data=data)
    except Exception as exc:
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")



@router.post("/memory/batch-retry", response_model=MemoryBatchSettingRead)
def retry_memory_batch(
    world_id: str,
    subject_id: str,
    data: MemoryBatchRetry,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryBatchSettingRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return memory_service.retry_memory_batch(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, data=data)
    except Exception as exc:
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")



@router.get("/memory/settings", response_model=MemorySettingRead)
def read_memory_setting(
    world_id: str,
    subject_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemorySettingRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return memory_service.read_memory_setting(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows)
    except (MemoryScopeError, MemoryValidationError) as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")



@router.put("/memory/settings", response_model=MemorySettingMutationRead)
def update_memory_setting(
    world_id: str,
    subject_id: str,
    data: MemorySettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemorySettingMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return memory_service.update_memory_setting(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, data=data)
    except Exception as exc:
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")



@router.get("/memories", response_model=MemoryItemListRead)
def list_memory_items(
    world_id: str,
    subject_id: str,
    request: Request,
    cursor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryItemListRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return memory_service.list_memory_items(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, cursor=cursor, limit=limit)
    except (MemoryNotFoundError, MemoryScopeError, MemoryValidationError) as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")



@router.get("/memories/{memory_id}", response_model=MemoryItemDetailRead)
def read_memory_item(
    world_id: str,
    subject_id: str,
    memory_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryItemDetailRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return memory_service.read_memory_item(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, memory_id=memory_id)
    except (MemoryNotFoundError, MemoryScopeError, MemoryValidationError) as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")



@router.put("/memories/{memory_id}/pin", response_model=MemoryItemMutationRead)
def update_memory_pin(
    world_id: str,
    subject_id: str,
    memory_id: str,
    data: MemoryPinUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryItemMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return memory_service.update_memory_pin(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, memory_id=memory_id, data=data)
    except Exception as exc:
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")



@router.post(
    "/memories/{memory_id}/corrections",
    response_model=MemoryItemMutationRead,
)
def correct_memory_item(
    world_id: str,
    subject_id: str,
    memory_id: str,
    data: MemoryCorrectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryItemMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return memory_service.correct_memory_item(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, memory_id=memory_id, data=data)
    except Exception as exc:
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")



@router.delete("/memories/{memory_id}", response_model=MemoryItemMutationRead)
def delete_memory_item(
    world_id: str,
    subject_id: str,
    memory_id: str,
    data: MemoryDeleteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    workflows: MemoryWorkflows = Depends(get_memory_workflows),
) -> MemoryItemMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return memory_service.delete_memory_item(scope=_scope(user, world_id, subject_id), db=db, workflows=workflows, memory_id=memory_id, data=data)
    except Exception as exc:
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")



__all__ = ["router"]
