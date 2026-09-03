"""P8-L-P World Chat response generation and public stream routes."""

from collections.abc import AsyncIterator
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, get_db
from app.core import browser_session
from app.core.config import settings
from app.domains.chat import public as chat
from app.domains.identity.public import User
from app.runtime.chat.composition import chat_service


router = APIRouter(prefix="/worlds/{world_id}/chat", tags=["world-chat"])


@router.post(
    "/threads/{thread_id}/messages",
    response_model=chat.WorldChatMessageAcceptRead,
)
def accept_world_message(
    world_id: str,
    thread_id: str,
    data: chat.WorldChatMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.WorldChatMessageAcceptRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return chat_service.accept_world_message(db, user, world_id, thread_id, data)
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except chat.MessageInFlightError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except chat.MessageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/threads/{thread_id}/retry",
    response_model=chat.WorldChatMessageAcceptRead,
)
def retry_world_response(
    world_id: str,
    thread_id: str,
    data: chat.WorldChatRetryCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.WorldChatMessageAcceptRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return chat_service.retry_world_response(db, user, world_id, thread_id, data)
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (chat.MessageInFlightError, chat.MessageValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/threads/{thread_id}/requests/latest",
    response_model=chat.WorldChatLatestRequestRead,
)
def get_latest_world_response_request(
    world_id: str,
    thread_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.WorldChatLatestRequestRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return chat_service.get_latest_world_response_request(
            db, user, world_id, thread_id
        )
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/threads/{thread_id}/requests/{request_id}",
    response_model=chat.WorldChatGenerationRequestRead,
)
def get_world_response_request(
    world_id: str,
    thread_id: str,
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.WorldChatGenerationRequestRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return chat_service.get_world_response_request(
            db, user, world_id, thread_id, request_id
        )
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/threads/{thread_id}/requests/{request_id}/evidence",
    response_model=chat.WorldChatEvidenceRead,
)
def get_world_response_evidence(
    world_id: str,
    thread_id: str,
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> chat.WorldChatEvidenceRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return chat_service.get_world_response_evidence(
            db, user, world_id, thread_id, request_id
        )
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/threads/{thread_id}/requests/{request_id}/events")
def stream_world_response_events(
    world_id: str,
    thread_id: str,
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        read = chat_service.get_world_response_request(
            db, user, world_id, thread_id, request_id
        )
    except chat.MessageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except chat.MessageForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    terminal = {"committed", "rejected", "cancelled", "timed_out", "failed", "orphaned"}
    if read.state != "accepted" and read.state not in terminal:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="response_request_already_running",
        )
    composition = getattr(request.app.state, "runtime_composition", None)
    memory_recall_service = (
        None if composition is None else composition.memory_recall_service
    )
    runtime_settings = settings if composition is None else composition.settings

    async def encoded() -> AsyncIterator[bytes]:
        events = chat_service.stream_world_response(
            db,
            user,
            world_id,
            thread_id,
            request_id,
            memory_recall_service=memory_recall_service,
            runtime_settings=runtime_settings,
        )
        async for event in events:
            payload = {
                "protocol_version": event.protocol_version,
                "request_id": event.request_id,
                "request_scope_hash": event.request_scope_hash,
                "generation_id": event.generation_id,
                "attempt_number": event.attempt_number,
                "sequence": event.sequence,
                "type": event.event_type.value,
                "payload": event.payload,
            }
            yield (
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")

    return StreamingResponse(
        encoded(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["router"]
