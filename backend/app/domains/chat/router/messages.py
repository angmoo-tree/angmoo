from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.domains.chat import exceptions as errors
from app.domains.chat import schemas as chat
from app.domains.chat.contracts.context import ChatUser as User
from app.domains.chat.dependencies import (
    get_current_user,
    get_db,
    get_message_service,
    get_settings_service,
    get_thread_service,
)
from app.domains.chat.service.messages import MessageService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService

router = APIRouter(tags=["messages"])


@router.get(
    "/messages/threads",
    response_model=chat.MessageThreadListRead,
)
def list_threads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> chat.MessageThreadListRead:
    return thread_service.list_threads(db, user)


@router.post(
    "/messages/threads",
    response_model=chat.MessageThreadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_thread(
    data: chat.MessageThreadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> chat.MessageThreadRead:
    try:
        return thread_service.create_or_get_thread(db, user, data)
    except errors.MessageThreadLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/messages/threads/{thread_id}",
    response_model=chat.MessageThreadRead,
)
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> chat.MessageThreadRead:
    try:
        return thread_service.get_thread(db, user, thread_id)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.patch(
    "/messages/threads/{thread_id}",
    response_model=chat.MessageThreadRead,
)
def update_thread(
    thread_id: str,
    data: chat.MessageThreadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> chat.MessageThreadRead:
    try:
        return thread_service.update_thread(db, user, thread_id, data)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
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
    user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
) -> Response:
    try:
        thread_service.delete_thread(db, user, thread_id)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/messages/threads/{thread_id}/messages",
    response_model=chat.MessageSendRead,
)
async def send_message(
    thread_id: str,
    data: chat.MessageMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service),
) -> chat.MessageSendRead:
    try:
        return await message_service.send_message(db, user, thread_id, data)
    except errors.MessageInFlightError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageCredentialRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageCredentialInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except errors.MessageModelBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/messages/threads/{thread_id}/messages/{message_id}/retry",
    response_model=chat.MessageSendRead,
)
async def retry_message(
    thread_id: str,
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service),
) -> chat.MessageSendRead:
    try:
        return await message_service.retry_message(db, user, thread_id, message_id)
    except errors.MessageInFlightError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageCredentialRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageCredentialInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except errors.MessageModelBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/messages/settings",
    response_model=chat.MessageSettingsRead,
)
def get_message_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings_service: MessageSettingsService = Depends(get_settings_service),
) -> chat.MessageSettingsRead:
    return settings_service.get_user_settings(db, user)


@router.patch(
    "/messages/settings",
    response_model=chat.MessageSettingsRead,
)
def update_message_settings(
    data: chat.MessageSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings_service: MessageSettingsService = Depends(get_settings_service),
) -> chat.MessageSettingsRead:
    try:
        return settings_service.update_user_settings(db, user, data)
    except errors.MessageCredentialRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/characters/{character_id}/message-settings",
    response_model=chat.CharacterMessageSettingRead,
)
def get_character_message_settings(
    character_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings_service: MessageSettingsService = Depends(get_settings_service),
) -> chat.CharacterMessageSettingRead:
    try:
        return settings_service.get_character_message_settings(db, user, character_id)
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.patch(
    "/characters/{character_id}/message-settings",
    response_model=chat.CharacterMessageSettingRead,
)
def update_character_message_settings(
    character_id: str,
    data: chat.CharacterMessageSettingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings_service: MessageSettingsService = Depends(get_settings_service),
) -> chat.CharacterMessageSettingRead:
    try:
        return settings_service.update_character_message_settings(
            db, user, character_id, data
        )
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
