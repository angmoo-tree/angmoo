"""P8-L-P World Chat response generation and public stream routes."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.chat import exceptions as errors
from app.domains.chat import schemas as chat
from app.domains.chat.contracts.context import ChatUser as User
from app.domains.chat.dependencies import (
    browser_session,
    get_current_user,
    get_db,
    get_evidence_service,
    get_generation_service,
)
from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.generation import GenerationService

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
    generation_service: GenerationService = Depends(get_generation_service),
) -> chat.WorldChatMessageAcceptRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return generation_service.accept_world_message(
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
    generation_service: GenerationService = Depends(get_generation_service),
) -> chat.WorldChatMessageAcceptRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return generation_service.retry_world_response(
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
    except (errors.MessageInFlightError, errors.MessageValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


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
    generation_service: GenerationService = Depends(get_generation_service),
) -> chat.WorldChatLatestRequestRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return generation_service.get_latest_world_response_request(
            db, user, world_id, thread_id
        )
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


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
    generation_service: GenerationService = Depends(get_generation_service),
) -> chat.WorldChatGenerationRequestRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return generation_service.get_world_response_request(
            db, user, world_id, thread_id, request_id
        )
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


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
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> chat.WorldChatEvidenceRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return evidence_service.get_world_response_evidence(
            db, user, world_id, thread_id, request_id
        )
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.get("/threads/{thread_id}/requests/{request_id}/events")
def stream_world_response_events(
    world_id: str,
    thread_id: str,
    request_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    generation_service: GenerationService = Depends(get_generation_service),
) -> StreamingResponse:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        read = generation_service.get_world_response_request(
            db, user, world_id, thread_id, request_id
        )
    except errors.MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except errors.MessageForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
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
        events = generation_service.stream_world_response(
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
