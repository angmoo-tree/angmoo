"""Persistence implementation owned by the Chat domain."""

from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)

__all__ = ["SqlAlchemyResponseLifecycleRepository"]
