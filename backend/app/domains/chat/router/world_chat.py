"""Canonical local World Chat v2 thread identity routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.domains.chat import exceptions as errors
from app.domains.chat import schemas as chat
from app.domains.chat.contracts.context import ChatUser as User
from app.domains.chat.dependencies import (
    browser_session,
    get_current_user,
    get_db,
    get_thread_service,
    get_search_preparation_service,
)
from app.domains.chat.service.threads import ThreadService
from app.domains.chat.contracts.search_preparation import SearchPreparationRequest, SearchPreparationRead

router = APIRouter(prefix="/worlds/{world_id}/chat", tags=["world-chat"])
entry_router = APIRouter(
    prefix="/worlds/{world_id}/world-characters",
    tags=["world-chat"],
)


@router.post("/threads/{thread_id}/memory-search/prepare", response_model=SearchPreparationRead)
async def prepare_memory_search(world_id: str, thread_id: str, data: SearchPreparationRequest,
        request: Request, response: Response, user=Depends(get_current_user),
        service=Depends(get_search_preparation_service)):
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        result = await service.prepare(user, world_id, thread_id)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from None
    except errors.MessageForbiddenError as exc:
        raise HTTPException(403, detail=str(exc)) from None
    except errors.MessageValidationError as exc:
        raise HTTPException(409, detail=str(exc)) from None
    if any(axis["status"] == "preparing" for axis in result["axes"].values()):
        response.status_code = 202
    return result


@entry_router.get(
    "/{responding_id}/chat-entry",
    response_model=chat.WorldChatEntryRead,
)
def get_world_chat_entry(
    world_id: str,
    responding_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chat_service: ThreadService = Depends(get_thread_service),
) -> chat.WorldChatEntryRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return chat_service.get_world_chat_entry(db, user, world_id, responding_id)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="target_profile_unavailable",
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get("/threads", response_model=chat.WorldChatThreadListRead)
def list_world_threads(
    world_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chat_service: ThreadService = Depends(get_thread_service),
) -> chat.WorldChatThreadListRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return chat_service.list_world_threads(db, user, world_id)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.post("/threads", response_model=chat.WorldChatThreadCreateRead)
def create_or_get_world_thread(
    world_id: str,
    data: chat.WorldChatThreadCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chat_service: ThreadService = Depends(get_thread_service),
) -> chat.WorldChatThreadCreateRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return chat_service.create_or_get_world_thread(db, user, world_id, data)
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageThreadLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageInFlightError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/threads/{thread_id}", response_model=chat.WorldChatThreadRead)
def get_world_thread(
    world_id: str,
    thread_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chat_service: ThreadService = Depends(get_thread_service),
) -> chat.WorldChatThreadRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return chat_service.get_world_thread(db, user, world_id, thread_id)
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.patch(
    "/threads/{thread_id}/model",
    response_model=chat.WorldChatThreadRead,
)
def update_world_thread_model(
    world_id: str,
    thread_id: str,
    data: chat.WorldChatThreadModelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chat_service: ThreadService = Depends(get_thread_service),
) -> chat.WorldChatThreadRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return chat_service.update_world_thread_model(
            db, user, world_id, thread_id, data
        )
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except errors.MessageInFlightError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except errors.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


__all__ = ["entry_router", "router"]
