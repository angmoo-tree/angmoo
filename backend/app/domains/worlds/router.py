"""World Creator HTTP endpoints; WorldCharacter endpoints have their own owner."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.identity_dependencies import get_current_user, get_optional_current_user
from app.database import get_db
from app.api.world_errors import _raise_world_error
from app.api.recommendation_dependencies import recommendation_workflows
from app.domains.worlds import schemas, service as world_service


router = APIRouter(prefix="/worlds", tags=["worlds"])
legacy_media_router = APIRouter(prefix="/media/worlds", tags=["worlds"])


@legacy_media_router.get("/{world_id}/{filename}", include_in_schema=False)
@router.get("/{world_id}/media/{filename}", response_class=FileResponse)
def read_world_media(
    world_id: str, filename: str,
    db: Session = Depends(get_db), user=Depends(get_optional_current_user),
) -> FileResponse:
    from app.domains.worlds.service.media import read_world_media as read
    try:
        path, content_type = read(db, world_id=world_id, filename=filename, user=user)
        return FileResponse(path, media_type=content_type, headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        })
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)
        raise AssertionError("unreachable")


@router.post("/default-space/ensure", response_model=schemas.WorldRead)
def ensure_default_space(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.domains.worlds.service.default_space import ensure_default_space as ensure
    try:
        world = ensure(db, owner_id=user.id)
        return world_service.get_world_read(db, world_id=world.id, user=user)
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)




@router.post(
    "",
    response_model=schemas.WorldCreatorContextRead,
    status_code=status.HTTP_201_CREATED,
)
def create_world(
    data: schemas.WorldDraftCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    topics = Depends(recommendation_workflows),
) -> schemas.WorldCreatorContextRead:
    try:
        return world_service.create_world(db, user=user, data=data, on_created=topics.initialize_world)
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
async def publish_world(
    world_id: str,
    data: schemas.WorldMutationRequest,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    topics = Depends(recommendation_workflows),
) -> schemas.WorldCreatorContextRead:
    try:
        result = world_service.publish_world(
            db,
            world_id=world_id,
            user=user,
            data=data,
        )
        return result
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


@router.post("/{world_id}/icon", response_model=schemas.WorldCreatorContextRead)
def upload_world_icon(world_id: str, data: schemas.WorldBannerUpload,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return world_service.upload_world_banner(db, world_id=world_id, user=user, data=data, media_type="icon")
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)


@router.delete("/{world_id}/icon", response_model=schemas.WorldCreatorContextRead)
def remove_world_icon(world_id: str, data: schemas.WorldMutationRequest,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return world_service.remove_world_banner(db, world_id=world_id, user=user, data=data, media_type="icon")
    except world_service.WorldServiceError as exc:
        _raise_world_error(exc)


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
