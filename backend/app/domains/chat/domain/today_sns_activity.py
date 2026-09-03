"""Immutable Today SNS activity snapshot for one World Chat generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType

from app.domains.social.public import TodaySocialCoverageStatus


TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION = "today-sns-activity-snapshot.v1"
MAX_TODAY_ROUTER_ENTRIES = 12
MAX_TODAY_ENTRY_TEXT_CHARS = 900
MAX_TODAY_ROUTER_EXCERPT_CHARS = 180
MAX_TODAY_ROUTER_VIEW_CHARS = 12_000


@dataclass(frozen=True, slots=True)
class TodaySnsSubjectiveContext:
    motivation_kind: str
    motivation_text: str
    emotion_label: str
    emotion_text: str | None
    emotion_intensity: int | None


@dataclass(frozen=True, slots=True)
class TodaySnsActivityEntry:
    opaque_reference: str
    kind: str
    event_type: str
    source_type: str
    source_id: str
    source_revision: str
    occurred_at: datetime
    actor_label: str
    counterpart_label: str | None
    content_mode: str
    title: str | None
    body: str | None
    parent_title: str | None
    parent_body: str | None
    root_title: str | None
    root_body: str | None
    root_post_id: str | None
    source_post_id: str | None
    target_post_id: str | None
    content_complete: bool
    truncated: bool
    subjective_context: TodaySnsSubjectiveContext | None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or len(self.source_revision) != 64:
            raise ValueError("today_sns_entry_source_invalid")
        if not self.opaque_reference or not self.kind or not self.actor_label:
            raise ValueError("today_sns_entry_shape_invalid")

    def provider_payload(self, *, include_content: bool) -> dict:
        subjective = self.subjective_context
        payload = {
            "ref": self.opaque_reference,
            "kind": self.kind,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.astimezone(UTC).isoformat(),
            "actor": self.actor_label,
            "counterpart": self.counterpart_label,
            "content_mode": self.content_mode,
            "content_complete": self.content_complete,
            "truncated": self.truncated,
            "subjective_context_available": subjective is not None,
            "motivation_kind": (
                None if subjective is None else subjective.motivation_kind
            ),
            "emotion_label": None if subjective is None else subjective.emotion_label,
        }
        if include_content:
            payload.update(
                {
                    "title": self.title,
                    "body": self.body,
                    "parent_title": self.parent_title,
                    "parent_body": self.parent_body,
                    "root_title": self.root_title,
                    "root_body": self.root_body,
                    "motivation_text": (
                        None if subjective is None else subjective.motivation_text
                    ),
                    "emotion_text": (
                        None if subjective is None else subjective.emotion_text
                    ),
                    "emotion_intensity": (
                        None if subjective is None else subjective.emotion_intensity
                    ),
                }
            )
        else:
            payload.update(
                {
                    "title_excerpt": _excerpt(self.title),
                    "body_excerpt": _excerpt(self.body),
                    "parent_excerpt": _excerpt(self.parent_body),
                }
            )
        return payload


@dataclass(frozen=True, slots=True)
class TodaySnsActivitySnapshot:
    owner_id: str
    world_id: str
    subject_world_character_id: str
    timezone: str
    started_at: datetime
    complete_through: datetime
    counts: Mapping[str, int]
    coverage: Mapping[str, TodaySocialCoverageStatus]
    source_watermarks: Mapping[str, str | None]
    entries: tuple[TodaySnsActivityEntry, ...]
    overflow: bool
    snapshot_hash: str
    counts_exact: bool = True
    version: str = TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))
        object.__setattr__(self, "source_watermarks", MappingProxyType(dict(self.source_watermarks)))
        if self.version != TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION:
            raise ValueError("today_sns_snapshot_version_invalid")
        if self.started_at.tzinfo is None or self.complete_through.tzinfo is None:
            raise ValueError("today_sns_snapshot_timezone_required")
        if len(self.snapshot_hash) != 64 or self.snapshot_hash != compute_today_sns_hash(
            self
        ):
            raise ValueError("today_sns_snapshot_hash_mismatch")

    def router_view(self) -> dict:
        selected = list(self.entries[:MAX_TODAY_ROUTER_ENTRIES])
        payload = {
            "version": "today-sns-router-view.v1",
            "day_timezone": self.timezone,
            "counts": dict(self.counts),
            "counts_exact": self.counts_exact,
            "coverage": {
                key: value.value for key, value in sorted(self.coverage.items())
            },
            "entries": [
                item.provider_payload(include_content=False) for item in selected
            ],
            "omitted_count": max(0, len(self.entries) - len(selected)),
            "overflow": self.overflow,
            "snapshot_hash": self.snapshot_hash,
        }
        while len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > MAX_TODAY_ROUTER_VIEW_CHARS and selected:
            selected.pop()
            payload["entries"] = [item.provider_payload(include_content=False) for item in selected]
            payload["omitted_count"] = max(0, len(self.entries) - len(selected))
        return payload

    def response_manifest(self, *, included_references: tuple[str, ...] | None = None) -> dict:
        """Return completeness facts that concrete EvidenceItems cannot express."""

        included = set(included_references) if included_references is not None else {
            entry.opaque_reference for entry in self.entries
        }
        included_counts = {
            kind: sum(entry.kind == kind and entry.opaque_reference in included for entry in self.entries)
            for kind in self.counts
        }
        return {
            "version": "today-sns-response-manifest.v1",
            "day_timezone": self.timezone,
            "started_at": self.started_at.astimezone(UTC).isoformat(),
            "complete_through": self.complete_through.astimezone(UTC).isoformat(),
            "counts": dict(self.counts),
            "counts_exact": self.counts_exact,
            "coverage": {
                key: value.value for key, value in sorted(self.coverage.items())
            },
            "entry_count": len(self.entries),
            "included_detail_counts": included_counts,
            "detail_omitted_count": max(0, sum(self.counts.values()) - sum(included_counts.values())),
            "overflow": self.overflow,
            "snapshot_hash": self.snapshot_hash,
        }


def compute_today_sns_hash(snapshot: TodaySnsActivitySnapshot) -> str:
    return build_today_sns_hash(
        owner_id=snapshot.owner_id,
        world_id=snapshot.world_id,
        subject_world_character_id=snapshot.subject_world_character_id,
        timezone=snapshot.timezone,
        started_at=snapshot.started_at,
        complete_through=snapshot.complete_through,
        counts=snapshot.counts,
        coverage=snapshot.coverage,
        source_watermarks=snapshot.source_watermarks,
        entries=snapshot.entries,
        overflow=snapshot.overflow,
        counts_exact=snapshot.counts_exact,
        version=snapshot.version,
    )


def build_today_sns_hash(
    *,
    owner_id: str,
    world_id: str,
    subject_world_character_id: str,
    timezone: str,
    started_at: datetime,
    complete_through: datetime,
    counts: Mapping[str, int],
    coverage: Mapping[str, TodaySocialCoverageStatus],
    source_watermarks: Mapping[str, str | None],
    entries: tuple[TodaySnsActivityEntry, ...],
    overflow: bool,
    counts_exact: bool = True,
    version: str = TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION,
) -> str:
    payload = {
        "version": version,
        "owner_id": owner_id,
        "world_id": world_id,
        "subject_world_character_id": subject_world_character_id,
        "timezone": timezone,
        "started_at": started_at.astimezone(UTC).isoformat(),
        "complete_through": complete_through.astimezone(UTC).isoformat(),
        "counts": dict(counts),
        "counts_exact": counts_exact,
        "coverage": {
            key: value.value for key, value in sorted(coverage.items())
        },
        "source_watermarks": dict(source_watermarks),
        "entries": [
            {
                **item.provider_payload(include_content=True),
                "source_type": item.source_type,
                "source_id": item.source_id,
                "source_revision": item.source_revision,
                "root_post_id": item.root_post_id,
                "source_post_id": item.source_post_id,
                "target_post_id": item.target_post_id,
            }
            for item in entries
        ],
        "overflow": overflow,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _excerpt(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:MAX_TODAY_ROUTER_EXCERPT_CHARS]


__all__ = [
    "MAX_TODAY_ENTRY_TEXT_CHARS",
    "MAX_TODAY_ROUTER_EXCERPT_CHARS",
    "MAX_TODAY_ROUTER_VIEW_CHARS",
    "MAX_TODAY_ROUTER_ENTRIES",
    "TODAY_SNS_ACTIVITY_SNAPSHOT_VERSION",
    "TodaySnsActivityEntry",
    "TodaySnsActivitySnapshot",
    "TodaySnsSubjectiveContext",
    "build_today_sns_hash",
    "compute_today_sns_hash",
]
