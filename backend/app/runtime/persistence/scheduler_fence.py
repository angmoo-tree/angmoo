"""Process-local fence context and its single SQLAlchemy before-commit hook."""

from __future__ import annotations
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.domains.runtime.exceptions import SchedulerFenceRejectedError
from app.domains.runtime.repository import scheduler_lease as lease_repository
from app.domains.runtime.repository.scheduler_lease import _database_now
from app.domains.runtime.service.scheduler_lease import _lease_matches

_SchedulerFence = tuple[str, int]


_scheduler_fence: ContextVar[_SchedulerFence | None] = ContextVar(
    "angmoo_scheduler_fence",
    default=None,
)


@contextmanager
def scheduler_fence(*, owner_id: str, fencing_epoch: int) -> Iterator[None]:
    token = _scheduler_fence.set((owner_id, fencing_epoch))
    try:
        yield
    finally:
        _scheduler_fence.reset(token)


@event.listens_for(Session, "before_commit")
def _verify_scheduler_fence_before_commit(db: Session) -> None:
    expected = _scheduler_fence.get()
    if expected is None:
        return
    owner_id, fencing_epoch = expected
    row = lease_repository.fence_row(db)
    now = _database_now(db)
    if not _lease_matches(row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now):
        raise SchedulerFenceRejectedError("scheduler lease fence rejected commit")
