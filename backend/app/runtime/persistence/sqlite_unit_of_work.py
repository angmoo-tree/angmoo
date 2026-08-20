"""SQLite transaction adapter for the canonical UnitOfWork port."""

from __future__ import annotations

from sqlalchemy.orm import Session


class SqliteUnitOfWork:
    def __init__(self, session: Session) -> None:
        if session.bind is None or session.bind.dialect.name != "sqlite":
            raise ValueError("SqliteUnitOfWork requires a SQLite session")
        self.session = session

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, entity: object) -> None:
        self.session.refresh(entity)


__all__ = ["SqliteUnitOfWork"]
