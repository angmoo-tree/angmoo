from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.domains.identity.dependencies import get_current_user
from app.core.db import get_db
from app.domains.chat import public as chat
from app.domains.identity.public import User
from app.runtime.chat.composition import chat_service


router = APIRouter(tags=["messages"])


@router.get(
    "/messages/threads",
    response_model=chat.MessageThreadListRead,
)
def list_threads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.MessageThreadListRead:
    return chat_service.list_threads(db, user)


@router.post(
    "/messages/threads",
    response_model=chat.MessageThreadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_thread(
    data: chat.MessageThreadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.MessageThreadRead:
    try:
        return chat_service.create_or_get_thread(db, user, data)
    except chat.MessageThreadLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
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
) -> chat.MessageThreadRead:
    try:
        return chat_service.get_thread(db, user, thread_id)
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/messages/threads/{thread_id}",
    response_model=chat.MessageThreadRead,
)
def update_thread(
    thread_id: str,
    data: chat.MessageThreadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.MessageThreadRead:
    try:
        return chat_service.update_thread(db, user, thread_id, data)
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
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
) -> Response:
    try:
        chat_service.delete_thread(db, user, thread_id)
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
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
) -> chat.MessageSendRead:
    try:
        return await chat_service.send_message(db, user, thread_id, data)
    except chat.MessageInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageCredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageCredentialInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except chat.MessageModelBusyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
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
) -> chat.MessageSendRead:
    try:
        return await chat_service.retry_message(db, user, thread_id, message_id)
    except chat.MessageInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageCredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageCredentialInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except chat.MessageModelBusyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
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
) -> chat.MessageSettingsRead:
    return chat_service.get_user_settings(db, user)


@router.patch(
    "/messages/settings",
    response_model=chat.MessageSettingsRead,
)
def update_message_settings(
    data: chat.MessageSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.MessageSettingsRead:
    try:
        return chat_service.update_user_settings(db, user, data)
    except chat.MessageCredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
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
) -> chat.CharacterMessageSettingRead:
    try:
        return chat_service.get_character_message_settings(db, user, character_id)
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/characters/{character_id}/message-settings",
    response_model=chat.CharacterMessageSettingRead,
)
def update_character_message_settings(
    character_id: str,
    data: chat.CharacterMessageSettingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.CharacterMessageSettingRead:
    try:
        return chat_service.update_character_message_settings(
            db, user, character_id, data
        )
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
