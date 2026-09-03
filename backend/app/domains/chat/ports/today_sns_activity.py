"""Chat-owned port for factual Today SNS activity reads."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domains.social.public import TodaySocialActivityRead
from app.domains.chat.domain.today_sns_activity import TodaySnsActivitySnapshot


class TodaySnsSnapshotChangedError(ValueError):
    """A source changed after the immutable generation snapshot was built."""


class TodaySnsActivityReaderPort(Protocol):
    def read(
        self,
        *,
        owner_id: str,
        world_id: str,
        subject_world_character_id: str,
        started_at: datetime,
        complete_through: datetime,
    ) -> TodaySocialActivityRead: ...


class TodaySnsSnapshotValidatorPort(Protocol):
    def assert_current(self, snapshot: TodaySnsActivitySnapshot) -> None: ...


__all__ = [
    "TodaySnsActivityReaderPort", "TodaySnsSnapshotChangedError",
    "TodaySnsSnapshotValidatorPort",
]
