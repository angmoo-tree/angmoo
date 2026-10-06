"""Owned World thread deletion, separate from the preserved Chat HTTP surface."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.domains.chat import exceptions as errors
from app.domains.chat import schemas as chat
from app.domains.chat.contracts.context import ChatUser as User
from app.domains.chat.dependencies import (
    browser_session,
    get_current_user,
    get_db,
    get_thread_service,
)
from app.domains.chat.service.threads import ThreadService

router = APIRouter(prefix="/worlds/{world_id}/chat", tags=["world-chat"])


@router.delete(
    "/threads/{thread_id}", response_model=chat.WorldChatThreadDeleteRead
)
def delete_world_thread(
    world_id: str,
    thread_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chat_service: ThreadService = Depends(get_thread_service),
) -> chat.WorldChatThreadDeleteRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return chat_service.delete_world_thread(db, user, world_id, thread_id)
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
