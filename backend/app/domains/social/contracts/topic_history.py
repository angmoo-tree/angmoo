"""Read-only creation-log fallback used after current Social columns."""

from __future__ import annotations
from typing import Protocol
from sqlalchemy.orm import Session


class CreationTopicLog(Protocol):
    @property
    def result(self) -> str | None: ...


class TopicHistoryReferences(Protocol):
    def latest_creation_log(
        self, db: Session, *, character_id: str, post_id: str
    ) -> CreationTopicLog | None: ...
