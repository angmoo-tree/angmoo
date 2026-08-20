"""Adapters that connect canonical outbox work to graph projection ports."""

from app.runtime.graph_projection.sqlalchemy_outbox import (
    SqlAlchemyProjectionOutbox,
    SqliteProjectionOutbox,
)

__all__ = ["SqlAlchemyProjectionOutbox", "SqliteProjectionOutbox"]
