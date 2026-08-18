from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db, get_optional_current_user
from app.domains.world_characters import public as world_character_setup
from app.domains.worlds import public as world_service


router = APIRouter(prefix="/worlds", tags=["worlds"])


def _raise_world_character_error(exc: world_character_setup.WorldCharacterSetupError) -> None:
    if isinstance(exc, world_character_setup.WorldCharacterSetupNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, world_character_setup.WorldCharacterSetupForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, world_character_setup.WorldCharacterSetupConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


@router.get(
    "/{world_id}/characters/{character_id}",
    response_model=schemas.WorldCharacterEntryRead,
)
def get_world_character_entry(
    world_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterEntryRead:
    try:
        return world_character_setup.get_world_entry(
            db,
            world_id=world_id,
            character_id=character_id,
            user=user,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_world_character_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/characters",
    response_model=schemas.WorldCharacterEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def enter_world_with_character(
    world_id: str,
    data: schemas.WorldCharacterEntryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterEntryRead:
    try:
        return world_character_setup.enter_world(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_character_setup.WorldCharacterSetupError as exc:
        _raise_world_character_error(exc)
        raise AssertionError("unreachable")


def _raise_world_error(exc: Exception) -> None:
    if isinstance(exc, world_service.WorldNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.reason_code,
        ) from exc
    if isinstance(
        exc,
        (
            world_service.WorldArchivedError,
            world_service.WorldRowVersionConflictError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.reason_code,
        ) from exc
    if isinstance(exc, world_service.WorldDefinitionIncompleteError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.reason_code,
                "readiness": exc.readiness.model_dump(mode="json"),
            },
        ) from exc
    if isinstance(
        exc,
        (
            world_service.WorldDefinitionValidationError,
            world_service.WorldBannerValidationError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.reason_code,
        ) from exc
    if isinstance(
        exc,
        (
            world_service.WorldMembershipRequiredError,
            world_service.WorldCreatorRoleRequiredError,
            world_service.WorldOwnerRoleRequiredError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.reason_code,
        ) from exc
    raise exc


@router.post(
    "",
    response_model=schemas.WorldCreatorContextRead,
    status_code=status.HTTP_201_CREATED,
)
def create_world(
    data: schemas.WorldDraftCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.create_world(db, user=user, data=data)
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.get("/{world_id}", response_model=schemas.WorldRead)
def get_world(
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_current_user),
) -> schemas.WorldRead:
    try:
        return world_service.get_world_read(db, world_id=world_id, user=user)
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/{world_id}/creator-context",
    response_model=schemas.WorldCreatorContextRead,
)
def get_world_creator_context(
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.get_creator_context(db, world_id=world_id, user=user)
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.patch(
    "/{world_id}",
    response_model=schemas.WorldCreatorContextRead,
)
def update_world(
    world_id: str,
    data: schemas.WorldUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.update_world(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/validate",
    response_model=schemas.WorldReadinessRead,
)
def validate_world_definition(
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldReadinessRead:
    try:
        return world_service.validate_world_definition(
            db,
            world_id=world_id,
            user=user,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/publish",
    response_model=schemas.WorldCreatorContextRead,
)
def publish_world(
    world_id: str,
    data: schemas.WorldMutationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.publish_world(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/archive",
    response_model=schemas.WorldCreatorContextRead,
)
def archive_world(
    world_id: str,
    data: schemas.WorldMutationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.archive_world(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{world_id}/banner",
    response_model=schemas.WorldCreatorContextRead,
)
def upload_world_banner(
    world_id: str,
    data: schemas.WorldBannerUpload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.upload_world_banner(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.delete(
    "/{world_id}/banner",
    response_model=schemas.WorldCreatorContextRead,
)
def remove_world_banner(
    world_id: str,
    data: schemas.WorldMutationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.remove_world_banner(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/{world_id}/generation-context",
    response_model=schemas.WorldGenerationContextRead,
)
def get_world_generation_context(
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldGenerationContextRead:
    try:
        return world_service.get_generation_context(
            db,
            world_id=world_id,
            user=user,
        )
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")
