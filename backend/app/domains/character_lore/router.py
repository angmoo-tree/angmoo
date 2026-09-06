from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.domains.character_lore import exceptions as lore_errors
from app.domains.character_lore import parser as lore_parser
from app.domains.character_lore import schemas
from app.domains.character_lore.contracts import LoreOwner, LoreWorkflows
from app.domains.character_lore.dependencies import (
    get_current_user,
    get_db,
    get_lore_workflows,
)
from app.domains.character_lore.service import documents as lore_service

router = APIRouter(prefix="/agents/{character_id}", tags=["agents"])


@router.get("/lore-sources", response_model=list[schemas.CharacterLoreSourceRead])
def list_lore_sources(
    character_id: str,
    db: Session = Depends(get_db),
    user: LoreOwner = Depends(get_current_user),
    workflows: LoreWorkflows = Depends(get_lore_workflows),
) -> list[schemas.CharacterLoreSourceRead]:
    try:
        return lore_service.list_lore_sources(
            db, user, character_id, workflows=workflows
        )
    except lore_errors.CharacterLoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc


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
    user: LoreOwner = Depends(get_current_user),
    workflows: LoreWorkflows = Depends(get_lore_workflows),
) -> schemas.CharacterLoreSourceRead:
    try:
        content = await lore_parser.read_lore_upload_bytes(file)
        return lore_service.upload_lore_source(
            db,
            user,
            character_id,
            filename=file.filename or "lore-file",
            content_type=file.content_type,
            file_bytes=content,
            replace_existing=replace_existing,
            workflows=workflows,
        )
    except lore_errors.CharacterLoreFileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except lore_errors.CharacterLoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    except lore_errors.CharacterLoreParserBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document parser capacity is temporarily unavailable",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except lore_errors.CharacterLoreValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    finally:
        await file.close()


@router.delete("/lore-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lore_source(
    character_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    user: LoreOwner = Depends(get_current_user),
    workflows: LoreWorkflows = Depends(get_lore_workflows),
) -> Response:
    try:
        lore_service.delete_lore_source(
            db, user, character_id, source_id, workflows=workflows
        )
    except lore_errors.CharacterLoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lore source not found"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/lore-sources/{source_id}/rebuild", response_model=schemas.CharacterLoreSourceRead
)
def rebuild_lore_source(
    character_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    user: LoreOwner = Depends(get_current_user),
    workflows: LoreWorkflows = Depends(get_lore_workflows),
) -> schemas.CharacterLoreSourceRead:
    try:
        return lore_service.rebuild_lore_source(
            db, user, character_id, source_id, workflows=workflows
        )
    except lore_errors.CharacterLoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lore source not found"
        ) from exc
    except lore_errors.CharacterLoreValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/lore-status", response_model=schemas.CharacterLoreStatusRead)
def get_lore_status(
    character_id: str,
    db: Session = Depends(get_db),
    user: LoreOwner = Depends(get_current_user),
    workflows: LoreWorkflows = Depends(get_lore_workflows),
) -> schemas.CharacterLoreStatusRead:
    try:
        return lore_service.lore_status(db, user, character_id, workflows=workflows)
    except lore_errors.CharacterLoreNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
