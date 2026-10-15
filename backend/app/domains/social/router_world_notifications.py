"""World notification routes with the existing browser/session boundary."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.api.identity_dependencies import browser_session
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.exceptions import SqliteBusyRetryExhausted
from app.domains.social.dependencies import get_current_user, get_db, get_world_notification_service
from app.domains.social.contracts.world_notifications import WorldNotificationError
from app.domains.social.schemas.world_notifications import (
    WorldNotificationPage, WorldNotificationCountRead, WorldNotificationReadResult, WorldUnreadCountsRead,
    WorldNotificationReadAllRequest, WorldNotificationReadAllResult,
)

def _local_frontend(request: Request):
    browser_session.require_local_frontend_request(request, mutation=request.method not in {"GET", "HEAD"})


router = APIRouter(tags=["world-notifications"], dependencies=[Depends(_local_frontend)])


def _respond(operation):
    try:
        return operation()
    except WorldNotificationError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code) from exc
    except SqliteBusyRetryExhausted as exc:
        raise HTTPException(status_code=503, detail="sqlite_busy_retry_exhausted") from exc


@router.get("/notifications/world-unread-counts", response_model=WorldUnreadCountsRead)
def world_unread_counts(world_ids: list[str] = Query(min_length=1, max_length=50),
        user=Depends(get_current_user), service=Depends(get_world_notification_service)):
    return _respond(lambda: service.batch(world_ids=world_ids, user_id=user.id))


@router.get("/worlds/{world_id}/notifications/unread-count", response_model=WorldNotificationCountRead)
def world_notification_count(world_id: str, user=Depends(get_current_user), service=Depends(get_world_notification_service)):
    return _respond(lambda: service.count(world_id=world_id, user_id=user.id))


@router.get("/worlds/{world_id}/notifications", response_model=WorldNotificationPage)
def world_notifications(world_id: str, limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
        user=Depends(get_current_user), service=Depends(get_world_notification_service)):
    return _respond(lambda: service.page(world_id=world_id, user_id=user.id, limit=limit, cursor=cursor))


@router.patch("/worlds/{world_id}/notifications/{notification_id}/read", response_model=WorldNotificationReadResult)
def read_world_notification(world_id: str, notification_id: int,
        user=Depends(get_current_user), service=Depends(get_world_notification_service), db=Depends(get_db)):
    return _respond(lambda: run_sqlite_session_immediate(db,
        lambda: service.mark_read(world_id=world_id, user_id=user.id, notification_id=notification_id)))


@router.post("/worlds/{world_id}/notifications/read-all", response_model=WorldNotificationReadAllResult)
def read_all_world_notifications(world_id: str, body: WorldNotificationReadAllRequest,
        user=Depends(get_current_user), service=Depends(get_world_notification_service), db=Depends(get_db)):
    return _respond(lambda: run_sqlite_session_immediate(db, lambda: service.mark_all_read(
        world_id=world_id, user_id=user.id, recipient_world_character_id=body.recipient_world_character_id)))
