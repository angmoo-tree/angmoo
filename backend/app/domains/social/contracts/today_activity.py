"""Provider-neutral factual records used to assemble Today's SNS context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from app.contracts.activity_thought import ActivityThought


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
class TodaySocialThoughtRecord:
    thought: ActivityThought
    source_digest: str
    thought_id: str


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
    thought: TodaySocialThoughtRecord | None = None
    parent_post_id: str | None = None
    # Canonical authors only; excluded from the existing provider/hash views.
    source_authors: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("today_social_activity_timezone_required")
        if not self.record_key or not self.source_id or len(self.source_revision) != 64:
            raise ValueError("today_social_activity_identity_invalid")
        validate_today_parent_identity({"source_post_id": self.source_post_id,
            "parent_post_id": self.parent_post_id, "parent_title": self.parent_title, "parent_body": self.parent_body})


def validate_today_parent_identity(record) -> None:
    parent = record.get("parent_post_id")
    if ((record.get("parent_body") or record.get("parent_title")) and not parent
        or parent and (not record.get("source_post_id") or parent == record["source_post_id"])):
        raise ValueError("today_social_activity_parent_identity_invalid")


def validate_today_activity_payload(payload) -> None:
    context = payload.get("context", payload)
    today = context.get("today_activity", {}) if isinstance(context, dict) else {}
    if isinstance(today, dict):
        for record in today.get("records", ()):
            validate_today_parent_identity(record)


@dataclass(frozen=True, slots=True)
class TodaySocialActivityRead:
    records: tuple[TodaySocialActivityRecord, ...]
    counts: dict[str, int]
    coverage: dict[str, TodaySocialCoverageStatus]
    source_watermarks: dict[str, str | None]
    overflow: bool
    counts_exact: bool = True
    thought_view: bool = False


__all__ = [
    "TodaySocialActivityKind",
    "TodaySocialActivityRead",
    "TodaySocialActivityRecord",
    "TodaySocialCoverageStatus",
    "TodaySocialSubjectiveRecord",
]
