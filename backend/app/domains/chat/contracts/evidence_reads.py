"""Same-Session reads used to revalidate a frozen Chat evidence excerpt."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.chat.contracts.today_sns_activity import TodaySnsActivityReaderPort
from app.domains.memory.contracts.inspector import MemoryItemDetail
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.source_evidence import MemorySourceEvidenceReaderPort


class RelationshipEvidenceState(Protocol):
    world_id: str
    actor_world_character_id: str
    target_world_character_id: str
    version: int


class ChatEvidenceReads(Protocol):
    def source_reader(self, db: Session) -> MemorySourceEvidenceReaderPort: ...
    def today_reader(self, db: Session) -> TodaySnsActivityReaderPort: ...
    def memory_detail(
        self,
        db: Session,
        source_reader: MemorySourceEvidenceReaderPort,
        scope: MemoryScope,
        *,
        item_id: str,
    ) -> MemoryItemDetail: ...
    def relationship_state(
        self, db: Session, source_id: object
    ) -> RelationshipEvidenceState | None: ...
    def world_character_name(
        self, db: Session, world_character_id: str | None, *, world_id: str
    ) -> str | None: ...
