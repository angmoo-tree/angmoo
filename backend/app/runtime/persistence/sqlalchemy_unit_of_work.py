"""SQLAlchemy implementation of the canonical transaction port."""

from __future__ import annotations

from sqlalchemy.orm import Session


class SqlAlchemyUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)


__all__ = ["SqlAlchemyUnitOfWork"]
