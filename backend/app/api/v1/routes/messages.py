from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import messages as message_service


router = APIRouter(tags=["messages"])


@router.get(
    "/messages/threads",
    response_model=schemas.MessageThreadListRead,
)
def list_threads(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageThreadListRead:
    return message_service.list_threads(db, user)


@router.post(
    "/messages/threads",
    response_model=schemas.MessageThreadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_thread(
    data: schemas.MessageThreadCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageThreadRead:
    try:
        return message_service.create_or_get_thread(db, user, data)
    except message_service.MessageThreadLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except message_service.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except message_service.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/messages/threads/{thread_id}",
    response_model=schemas.MessageThreadRead,
)
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageThreadRead:
    try:
        return message_service.get_thread(db, user, thread_id)
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/messages/threads/{thread_id}",
    response_model=schemas.MessageThreadRead,
)
def update_thread(
    thread_id: str,
    data: schemas.MessageThreadUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageThreadRead:
    try:
        return message_service.update_thread(db, user, thread_id, data)
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except message_service.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/messages/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Response:
    try:
        message_service.delete_thread(db, user, thread_id)
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/messages/threads/{thread_id}/messages",
    response_model=schemas.MessageSendRead,
)
async def send_message(
    thread_id: str,
    data: schemas.MessageMessageCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageSendRead:
    try:
        return await message_service.send_message(db, user, thread_id, data)
    except message_service.MessageInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except message_service.MessageCredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except message_service.MessageCredentialInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except message_service.MessageModelBusyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except message_service.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except message_service.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/messages/threads/{thread_id}/messages/{message_id}/retry",
    response_model=schemas.MessageSendRead,
)
async def retry_message(
    thread_id: str,
    message_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageSendRead:
    try:
        return await message_service.retry_message(db, user, thread_id, message_id)
    except message_service.MessageInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except message_service.MessageCredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except message_service.MessageCredentialInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except message_service.MessageModelBusyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except message_service.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except message_service.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/messages/settings",
    response_model=schemas.MessageSettingsRead,
)
def get_message_settings(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageSettingsRead:
    return message_service.get_user_settings(db, user)


@router.patch(
    "/messages/settings",
    response_model=schemas.MessageSettingsRead,
)
def update_message_settings(
    data: schemas.MessageSettingsUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.MessageSettingsRead:
    try:
        return message_service.update_user_settings(db, user, data)
    except message_service.MessageCredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except message_service.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except message_service.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/characters/{character_id}/message-settings",
    response_model=schemas.CharacterMessageSettingRead,
)
def get_character_message_settings(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CharacterMessageSettingRead:
    try:
        return message_service.get_character_message_settings(db, user, character_id)
    except message_service.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/characters/{character_id}/message-settings",
    response_model=schemas.CharacterMessageSettingRead,
)
def update_character_message_settings(
    character_id: str,
    data: schemas.CharacterMessageSettingUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CharacterMessageSettingRead:
    try:
        return message_service.update_character_message_settings(
            db, user, character_id, data
        )
    except message_service.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except message_service.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
