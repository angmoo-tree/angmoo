"""Concrete provider-free Memory producer for committed World Chat responses."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.chat.ports import SuccessfulChatMemorySource
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from app.domains.memory.public import (
    MemoryKindV1,
    MemoryScope,
    MemorySourceTypeV1,
    MemoryWriteLifecycleService,
)
from app.runtime.memory import SqlAlchemyMemorySourceEvidenceReader


class SqlAlchemySuccessfulChatMemoryProducer:
    """Create at most one idempotent candidate after the Chat commit succeeds."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def propose_after_commit(self, source: SuccessfulChatMemorySource) -> None:
        try:
            repository = SqlAlchemyMemoryRepository(self._session)
            MemoryWriteLifecycleService(
                repository,
                SqlAlchemyMemorySourceEvidenceReader(self._session),
            ).propose_candidate(
                scope=MemoryScope(
                    owner_id=source.owner_id,
                    world_id=source.world_id,
                    subject_world_character_id=source.subject_world_character_id,
                ),
                source_type=MemorySourceTypeV1.CHAT_MESSAGE,
                source_id=str(source.assistant_message_id),
                memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise


__all__ = ["SqlAlchemySuccessfulChatMemoryProducer"]
