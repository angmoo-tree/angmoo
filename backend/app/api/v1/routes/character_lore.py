from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import character_lore as lore_service


router = APIRouter(prefix="/agents/{character_id}", tags=["agents"])


@router.get("/lore-sources", response_model=list[schemas.CharacterLoreSourceRead])
def list_lore_sources(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.CharacterLoreSourceRead]:
    try:
        return lore_service.list_lore_sources(db, user, character_id)
    except lore_service.CharacterLoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.post(
    "/lore-sources",
    response_model=schemas.CharacterLoreSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_lore_source(
    character_id: str,
    file: UploadFile = File(...),
    replace_existing: bool = Form(False),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CharacterLoreSourceRead:
    try:
        content = await lore_service.read_lore_upload_bytes(file)
        return lore_service.upload_lore_source(
            db,
            user,
            character_id,
            filename=file.filename or "lore-file",
            content_type=file.content_type,
            file_bytes=content,
            replace_existing=replace_existing,
        )
    except lore_service.CharacterLoreFileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except lore_service.CharacterLoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except lore_service.CharacterLoreParserBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document parser capacity is temporarily unavailable",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except lore_service.CharacterLoreValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        await file.close()


@router.delete("/lore-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lore_source(
    character_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Response:
    try:
        lore_service.delete_lore_source(db, user, character_id, source_id)
    except lore_service.CharacterLoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lore source not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/lore-sources/{source_id}/rebuild",
    response_model=schemas.CharacterLoreSourceRead,
)
def rebuild_lore_source(
    character_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CharacterLoreSourceRead:
    try:
        return lore_service.rebuild_lore_source(db, user, character_id, source_id)
    except lore_service.CharacterLoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lore source not found") from exc
    except lore_service.CharacterLoreValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/lore-status", response_model=schemas.CharacterLoreStatusRead)
def get_lore_status(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CharacterLoreStatusRead:
    try:
        return lore_service.lore_status(db, user, character_id)
    except lore_service.CharacterLoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
