"""World Creator HTTP endpoints; WorldCharacter endpoints have their own owner."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.identity_dependencies import get_current_user, get_optional_current_user
from app.core.db import get_db
from app.api.world_errors import _raise_world_error
from app.domains.worlds import schemas, service as world_service


router = APIRouter(prefix="/worlds", tags=["worlds"])




@router.post(
    "",
    response_model=schemas.WorldCreatorContextRead,
    status_code=status.HTTP_201_CREATED,
)
def create_world(
    data: schemas.WorldDraftCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
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
    user = Depends(get_optional_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
    user = Depends(get_current_user),
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
