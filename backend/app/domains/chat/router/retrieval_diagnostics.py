"""Owner-only troubleshooting; deliberately separate from message/stream DTOs."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.domains.chat.schemas import CaptureUpdate, CaptureRead, DiagnosticRead
from sqlalchemy.orm import Session
from app.domains.chat.dependencies import browser_session, get_current_user, get_db, get_thread_service
from app.domains.chat.contracts.context import ChatUser
from app.domains.chat.exceptions import MessageForbiddenError, MessageNotFoundError, MessageValidationError
from app.domains.chat.service.threads import ThreadService
from app.domains.chat.service.diagnostic_capture import capture
from app.domains.chat.repository.retrieval_diagnostics import read
from app.domains.chat.repository.response_requests import _latest_request_row
from app.domains.chat.models import ChatResponseRequest

router = APIRouter(prefix="/worlds/{world_id}/chat/threads/{thread_id}", tags=["world-chat"])


def scope_access(world_id: str, thread_id: str, request: Request,
                 db: Session = Depends(get_db), user: ChatUser = Depends(get_current_user),
                 service: ThreadService = Depends(get_thread_service)):
    browser_session.require_local_frontend_request(request, mutation=request.method != "GET")
    try:
        service._require_world_chat_owner_scope(db, user.id, world_id)
        thread = service._get_owned_world_thread(db, user, world_id, thread_id)
        service._world_thread_read(db, thread, include_messages=False)
    except MessageNotFoundError as exc:
        raise HTTPException(404, "대화를 찾을 수 없습니다.") from exc
    except MessageValidationError as exc:
        capture.configure((user.id, world_id, thread_id), False)
        raise HTTPException(422, "현재 대화의 진단을 볼 수 없습니다.") from exc
    except MessageForbiddenError as exc:
        raise HTTPException(403, "이 대화의 진단을 볼 수 없습니다.") from exc
    return (user.id, world_id, thread_id)


@router.get("/diagnostics", response_model=DiagnosticRead)
def diagnostics(response: Response, request_id: str | None = None,
                scope=Depends(scope_access), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    row = db.get(ChatResponseRequest, request_id) if request_id else _latest_request_row(db, scope[2])
    if row is not None and row.thread_id != scope[2]:
        raise HTTPException(404, "응답 요청을 찾을 수 없습니다.")
    if request_id and row is None:
        raise HTTPException(404, "응답 요청을 찾을 수 없습니다.")
    result = {"status": "not_recorded", "record": None} if row is None else read(db, row.request_id)
    return {"world_id": scope[1], "thread_id": scope[2], "request_id": None if row is None else row.request_id,
            "request_state": None if row is None else row.state,
            "capture": capture.status(scope), "details": None if row is None else capture.read(scope, row.request_id), **result}


@router.put("/diagnostics/capture", response_model=CaptureRead)
def configure(data: CaptureUpdate, response: Response, scope=Depends(scope_access)):
    response.headers["Cache-Control"] = "no-store"
    return capture.configure(scope, data.enabled)


@router.delete("/diagnostics/capture", response_model=CaptureRead)
def clear(response: Response, scope=Depends(scope_access)):
    response.headers["Cache-Control"] = "no-store"
    return capture.configure(scope, False)
