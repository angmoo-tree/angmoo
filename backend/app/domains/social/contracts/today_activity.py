"""Provider-neutral factual records used to assemble Today's SNS context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TodaySocialActivityKind(StrEnum):
    POST_AUTHORED = "posts_authored"
    REPLY_AUTHORED = "replies_authored"
    REPLY_RECEIVED = "replies_received"
    MENTION_RECEIVED = "mentions_received"
    REACTION_GIVEN = "reactions_given"
    REACTION_RECEIVED = "reactions_received"
    REPOST = "reposts"
    FOLLOW = "follows"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)


class TodaySocialCoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class TodaySocialSubjectiveRecord:
    motivation_kind: str
    motivation_text: str
    emotion_label: str
    emotion_text: str | None
    emotion_intensity: int | None
    source_digest: str


@dataclass(frozen=True, slots=True)
class TodaySocialActivityRecord:
    record_key: str
    kind: TodaySocialActivityKind
    source_type: str
    source_id: str
    source_revision: str
    actor_world_character_id: str
    counterpart_world_character_id: str | None
    event_type: str
    occurred_at: datetime
    root_post_id: str | None = None
    source_post_id: str | None = None
    target_post_id: str | None = None
    title: str | None = None
    body: str | None = None
    parent_title: str | None = None
    parent_body: str | None = None
    root_title: str | None = None
    root_body: str | None = None
    subjective_context: TodaySocialSubjectiveRecord | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("today_social_activity_timezone_required")
        if not self.record_key or not self.source_id or len(self.source_revision) != 64:
            raise ValueError("today_social_activity_identity_invalid")


@dataclass(frozen=True, slots=True)
class TodaySocialActivityRead:
    records: tuple[TodaySocialActivityRecord, ...]
    counts: dict[str, int]
    coverage: dict[str, TodaySocialCoverageStatus]
    source_watermarks: dict[str, str | None]
    overflow: bool
    counts_exact: bool = True


__all__ = [
    "TodaySocialActivityKind",
    "TodaySocialActivityRead",
    "TodaySocialActivityRecord",
    "TodaySocialCoverageStatus",
    "TodaySocialSubjectiveRecord",
]
