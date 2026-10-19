"""Immutable, provider-safe evidence snapshot for one Character response."""

from __future__ import annotations
from app.contracts.search_diagnostics import evidence_lineage

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import re

from app.domains.chat.contracts.response_request import (
    DegradedReason,
    EvidenceCapability,
    RetrievalAxis,
    RetrievalOutcome,
)
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute


EVIDENCE_BUNDLE_VERSION = "evidence-bundle.v1"
MAX_EVIDENCE_ITEMS = 12
MAX_EVIDENCE_ITEM_CHARS = 2_000
MAX_EVIDENCE_BUNDLE_CHARS = 8_000


class EvidenceKind(StrEnum):
    CANONICAL_SOURCE = "canonical_source"
    EPISODE_MEMORY = "episode_memory"
    GRAPH_RELATIONSHIP = "graph_relationship"
    GRAPH_EVENT = "graph_event"
    TODAY_SNS_ACTIVITY = "today_sns_activity"
    CURRENT_IMAGE = "current_image_analysis"


class EvidenceLocatorKind(StrEnum):
    CANONICAL_SOURCE = "canonical_source"
    GRAPH_RELATIONSHIP = "graph_relationship"
    MEMORY_ITEM = "memory_item"
    IMAGE_ASSET = "image_asset"


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    kind: EvidenceLocatorKind
    source_id: str
    source_type: str | None = None
    source_revision: str | None = None
    actor_world_character_id: str | None = None
    target_world_character_id: str | None = None
    # Private prepared facts, retained until situation delivery is frozen.
    relationship_facts_digest: str | None = None
    relationship_view_version: int | None = None

    def __post_init__(self) -> None:
        if not self.source_id or len(self.source_id) > 128:
            raise EvidenceBundleContractError("evidence_locator_id_invalid")
        if self.kind is EvidenceLocatorKind.CANONICAL_SOURCE and not self.source_type:
            raise EvidenceBundleContractError("evidence_locator_source_type_missing")
        if self.source_revision is not None and (
            not self.source_revision or len(self.source_revision) > 128
        ):
            raise EvidenceBundleContractError("evidence_locator_revision_invalid")
        if self.kind is EvidenceLocatorKind.GRAPH_RELATIONSHIP and (
            not self.actor_world_character_id or not self.target_world_character_id
        ):
            raise EvidenceBundleContractError("evidence_locator_relationship_invalid")
        if self.relationship_facts_digest is not None and (
            self.kind is not EvidenceLocatorKind.GRAPH_RELATIONSHIP
            or len(self.relationship_facts_digest) != 64
            or type(self.relationship_view_version) is not int or self.relationship_view_version < 0
        ):
            raise EvidenceBundleContractError("evidence_locator_relationship_basis_invalid")


class EvidenceBundleContractError(ValueError):
    """Stable fail-closed error for unsafe or malformed evidence."""


_EVIDENCE_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)


def validate_evidence_time_provenance(value: object) -> None:
    """Validate code-owned time facts without coercing or changing their hash input."""
    if not isinstance(value, dict) or set(value) != {"kind", "event_from", "event_to", "recorded_at"}:
        raise EvidenceBundleContractError("evidence_time_provenance_invalid")
    kind = value["kind"]
    if type(kind) is not str or kind not in {"event", "interval", "recorded", "unknown"}:
        raise EvidenceBundleContractError("evidence_time_provenance_invalid")
    parsed: dict[str, datetime | None] = {}
    for key in ("event_from", "event_to", "recorded_at"):
        timestamp = value[key]
        if timestamp is None:
            parsed[key] = None
            continue
        if type(timestamp) is not str or len(timestamp) > 40 or not _EVIDENCE_TIMESTAMP.fullmatch(timestamp):
            raise EvidenceBundleContractError("evidence_time_provenance_invalid")
        try:
            parsed[key] = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise EvidenceBundleContractError("evidence_time_provenance_invalid") from exc
    start, end, recorded = (parsed[key] for key in ("event_from", "event_to", "recorded_at"))
    if (
        (kind == "event" and (start is None or (end is not None and end != start)))
        or (kind == "interval" and (start is None or end is None or end < start))
        or (kind in {"recorded", "unknown"} and (start is not None or end is not None))
        or (kind == "recorded" and recorded is None)
    ):
        raise EvidenceBundleContractError("evidence_time_provenance_invalid")
    # Unknown event time can still retain a known recording timestamp. It must
    # never turn that recording timestamp into the event's time.


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    opaque_reference: str
    kind: EvidenceKind
    text: str
    occurred_at: datetime | None
    axes: tuple[RetrievalAxis, ...]
    source_succeeded: bool = True
    observable: bool = True
    locator: EvidenceLocator | None = None
    # Optional, server-verified authors. Not part of v1 text/hash/serialization.
    author_identities: tuple[tuple[str, str], ...] = ()
    relationship_projection: dict | None = None
    display_projection: dict | None = None
    # Prepared canonical times are private until a v4 bundle binds them.
    prepared_times: tuple[str, str | None, str | None, str | None] | None = None
    time_provenance: tuple[str, str | None, str | None, str | None] | None = None

    def __post_init__(self) -> None:
        if (
            not self.opaque_reference
            or len(self.opaque_reference) > 96
            or not self.text.strip()
            or len(self.text) > (MAX_EVIDENCE_BUNDLE_CHARS if self.kind is EvidenceKind.EPISODE_MEMORY else MAX_EVIDENCE_ITEM_CHARS)
        ):
            raise EvidenceBundleContractError("evidence_item_shape_invalid")
        if not self.source_succeeded or not self.observable:
            raise EvidenceBundleContractError("evidence_item_untrusted")
        if not self.axes or len(set(self.axes)) != len(self.axes):
            raise EvidenceBundleContractError("evidence_item_axes_invalid")
        if self.occurred_at is not None and self.occurred_at.tzinfo is None:
            raise EvidenceBundleContractError("evidence_item_timezone_required")
        for times in (self.prepared_times, self.time_provenance):
            if times is not None and (not isinstance(times, tuple) or len(times) != 4
                or type(times[0]) is not str or times[0] not in {"event", "interval", "recorded", "unknown"}
                or any(value is not None and (type(value) is not str or len(value) > 40) for value in times[1:])):
                raise EvidenceBundleContractError("evidence_time_provenance_invalid")
        if self.time_provenance is not None:
            validate_evidence_time_provenance(_time_payload(self.time_provenance))

    @property
    def normalized_text(self) -> str:
        return " ".join(self.text.split())


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    request_id: str
    request_scope_hash: str
    route: RetrievalRoute
    retrieval_outcome: RetrievalOutcome
    items: tuple[EvidenceItem, ...]
    partial_axes: tuple[RetrievalAxis, ...] = ()
    degraded_reason: DegradedReason | None = None
    clarification_slot: str | None = None
    version: str = EVIDENCE_BUNDLE_VERSION
    evidence_hash: str = ""
    preserve_rank_order: bool = False

    def __post_init__(self) -> None:
        if self.version != EVIDENCE_BUNDLE_VERSION:
            raise EvidenceBundleContractError("evidence_bundle_version_invalid")
        if not self.request_id or len(self.request_scope_hash) != 64:
            raise EvidenceBundleContractError("evidence_bundle_identity_invalid")
        if len(self.items) > MAX_EVIDENCE_ITEMS:
            raise EvidenceBundleContractError("evidence_bundle_item_limit_exceeded")
        if sum(len(item.text) for item in self.items) > MAX_EVIDENCE_BUNDLE_CHARS:
            raise EvidenceBundleContractError("evidence_bundle_char_limit_exceeded")
        if len(set(self.partial_axes)) != len(self.partial_axes):
            raise EvidenceBundleContractError("evidence_bundle_partial_axis_duplicate")
        if (self.route is RetrievalRoute.CLARIFICATION) != (
            self.retrieval_outcome is RetrievalOutcome.CLARIFICATION_REQUIRED
        ):
            raise EvidenceBundleContractError(
                "evidence_bundle_clarification_route_mismatch"
            )
        if self.route is RetrievalRoute.CLARIFICATION and not self.clarification_slot:
            raise EvidenceBundleContractError("evidence_bundle_clarification_missing")
        if self.degraded_reason is not None and self.retrieval_outcome not in {
            RetrievalOutcome.DEGRADED,
            RetrievalOutcome.NO_EVIDENCE,
        }:
            raise EvidenceBundleContractError(
                "evidence_bundle_degraded_reason_forbidden"
            )
        expected = compute_evidence_hash(
            request_id=self.request_id,
            request_scope_hash=self.request_scope_hash,
            route=self.route,
            retrieval_outcome=self.retrieval_outcome,
            items=self.items,
            partial_axes=self.partial_axes,
            degraded_reason=self.degraded_reason,
            clarification_slot=self.clarification_slot,
        )
        if self.evidence_hash != expected:
            raise EvidenceBundleContractError("evidence_bundle_hash_mismatch")

    @property
    def public_evidence_count(self) -> int:
        return len(self.items)

    @property
    def evidence_capability(self) -> EvidenceCapability:
        if not self.items:
            return EvidenceCapability.NONE
        if self.degraded_reason is not None:
            return EvidenceCapability.DEGRADED
        return EvidenceCapability.AVAILABLE

    def provider_payload(self) -> dict:
        """Return only bounded prose and opaque refs, never canonical identifiers."""

        return {
            "version": self.version,
            "route": self.route.value,
            "retrieval_outcome": self.retrieval_outcome.value,
            "items": [
                {
                    "ref": item.opaque_reference,
                    "kind": item.kind.value,
                    "text": item.text,
                    **({"time_provenance": _time_payload(item.time_provenance)} if item.time_provenance else {}),
                    "occurred_at": (
                        None
                        if item.occurred_at is None
                        else item.occurred_at.astimezone(UTC).isoformat()
                    ),
                }
                for item in self.items
            ],
            "partial_axes": [axis.value for axis in self.partial_axes],
            "degraded": self.degraded_reason is not None,
            "clarification_slot": self.clarification_slot,
        }

    def inspector_snapshot(self) -> dict:
        """Private persistence payload used only by the authenticated inspector.

        Unlike ``provider_payload`` this contains typed locators so the source
        can be revalidated later.  Callers must never serialize it through a
        normal generation response DTO.
        """

        evidence_lineage("inspector", self.items)
        return {
            "version": "evidence-inspector.v2",
            "items": [
                {
                    "ref": item.opaque_reference,
                    "kind": item.kind.value,
                    "text": item.normalized_text,
                    **({"display_projection": item.display_projection} if item.display_projection is not None else {}),
                    **({"time_provenance": _time_payload(item.time_provenance)} if item.time_provenance else {}),
                    "occurred_at": (
                        None
                        if item.occurred_at is None
                        else item.occurred_at.astimezone(UTC).isoformat()
                    ),
                    "axes": [axis.value for axis in item.axes],
                    "locator": (
                        None
                        if item.locator is None
                        else {
                            "kind": item.locator.kind.value,
                            "source_type": item.locator.source_type,
                            "source_id": item.locator.source_id,
                            "source_revision": item.locator.source_revision,
                            "actor_world_character_id": (
                                item.locator.actor_world_character_id
                            ),
                            "target_world_character_id": (
                                item.locator.target_world_character_id
                            ),
                        }
                    ),
                }
                for item in self.items
            ],
        }


    def with_temporal_evidence(self):
        items = tuple(replace(item, time_provenance=item.prepared_times or (
            ("unknown", None, None, None) if item.occurred_at is None or item.kind is EvidenceKind.EPISODE_MEMORY else
            ("event", item.occurred_at.astimezone(UTC).isoformat(), None, None))) for item in self.items)
        digest = compute_evidence_hash(request_id=self.request_id, request_scope_hash=self.request_scope_hash,
            route=self.route, retrieval_outcome=self.retrieval_outcome, items=items,
            partial_axes=self.partial_axes, degraded_reason=self.degraded_reason, clarification_slot=self.clarification_slot)
        return replace(self, items=items, evidence_hash=digest)


def _time_payload(value):
    return dict(zip(("kind", "event_from", "event_to", "recorded_at"), value, strict=True))


def compute_evidence_hash(
    *,
    request_id: str,
    request_scope_hash: str,
    route: RetrievalRoute,
    retrieval_outcome: RetrievalOutcome,
    items: tuple[EvidenceItem, ...],
    partial_axes: tuple[RetrievalAxis, ...],
    degraded_reason: DegradedReason | None,
    clarification_slot: str | None,
) -> str:
    payload = {
        "version": EVIDENCE_BUNDLE_VERSION,
        "request_id": request_id,
        "request_scope_hash": request_scope_hash,
        "route": route.value,
        "retrieval_outcome": retrieval_outcome.value,
        "items": [
            {
                "opaque_reference": item.opaque_reference,
                "kind": item.kind.value,
                "text": item.normalized_text,
                **({"time_provenance": _time_payload(item.time_provenance)} if item.time_provenance else {}),
                "occurred_at": (
                    None
                    if item.occurred_at is None
                    else item.occurred_at.astimezone(UTC).isoformat()
                ),
                "axes": [axis.value for axis in item.axes],
            }
            for item in items
        ],
        "partial_axes": [axis.value for axis in partial_axes],
        "degraded_reason": (
            None if degraded_reason is None else degraded_reason.value
        ),
        "clarification_slot": clarification_slot,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def opaque_evidence_reference(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"evidence-{digest}"


__all__ = [
    "EVIDENCE_BUNDLE_VERSION",
    "MAX_EVIDENCE_BUNDLE_CHARS",
    "MAX_EVIDENCE_ITEM_CHARS",
    "MAX_EVIDENCE_ITEMS",
    "EvidenceBundle",
    "EvidenceBundleContractError",
    "EvidenceItem",
    "EvidenceKind",
    "EvidenceLocator",
    "EvidenceLocatorKind",
    "compute_evidence_hash",
    "opaque_evidence_reference",
    "validate_evidence_time_provenance",
]
