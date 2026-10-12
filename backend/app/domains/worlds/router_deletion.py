"""Deletion commands use ordinary authenticated/Origin-checked API transport."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.identity_dependencies import get_current_user
from app.domains.worlds.contracts_deletion import WorldDeletionCommand, WorldDeletionReceipt, WorldDeletionPreview, WorldDeletionError
from app.domains.worlds.service import deletion

router = APIRouter(tags=["world-deletion"])


def _translate(operation):
    try:
        return operation()
    except WorldDeletionError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code) from exc


@router.get("/worlds/{world_id}/deletion-preview", response_model=WorldDeletionPreview)
def preview(world_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _translate(lambda: deletion.preview(db, world_id, user.id))


@router.delete("/worlds/{world_id}", response_model=WorldDeletionReceipt, status_code=status.HTTP_202_ACCEPTED)
def accept(world_id: str, command: WorldDeletionCommand, request: Request,
    db: Session = Depends(get_db), user=Depends(get_current_user)):
    result = _translate(lambda: deletion.accept(db, world_id, user.id, command,
        stop_admission=request.app.state.world_deletion_stop_admission))
    notify = getattr(request.app.state, "world_deletion_notify", None)
    if notify:
        notify(result.world_id)  # After commit; rejected admission cancels no work.
    return result


@router.get("/world-deletions", response_model=list[WorldDeletionReceipt])
def unfinished(active: bool = True, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return deletion.unfinished(db, user.id)


@router.get("/world-deletions/{request_id}", response_model=WorldDeletionReceipt)
def read(request_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _translate(lambda: deletion.receipt(deletion.owned_receipt(db, request_id, user.id)))


@router.post("/world-deletions/{request_id}/retry", response_model=WorldDeletionReceipt, status_code=202)
def retry(request_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _translate(lambda: deletion.retry(db, request_id, user.id))
