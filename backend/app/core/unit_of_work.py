from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.orm import Session


_DEFER_COMMITS: ContextVar[bool] = ContextVar("defer_commits", default=False)


@contextmanager
def deferred_commits() -> Iterator[None]:
    token = _DEFER_COMMITS.set(True)
    try:
        yield
    finally:
        _DEFER_COMMITS.reset(token)


def finish_write(db: Session, entity: object | None = None) -> None:
    if _DEFER_COMMITS.get():
        db.flush()
    else:
        db.commit()
    if entity is not None:
        db.refresh(entity)
