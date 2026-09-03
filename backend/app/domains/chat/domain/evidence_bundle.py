"""Immutable, provider-safe evidence snapshot for one Character response."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json

from app.domains.chat.domain.response_request import (
    DegradedReason,
    EvidenceCapability,
    RetrievalAxis,
    RetrievalOutcome,
)
from app.domains.chat.domain.retrieval_intent import RetrievalRoute


EVIDENCE_BUNDLE_VERSION = "evidence-bundle.v1"
MAX_EVIDENCE_ITEMS = 12
MAX_EVIDENCE_ITEM_CHARS = 2_000
MAX_EVIDENCE_BUNDLE_CHARS = 8_000


class EvidenceKind(StrEnum):
    CANONICAL_SOURCE = "canonical_source"
    GRAPH_RELATIONSHIP = "graph_relationship"
    GRAPH_EVENT = "graph_event"


class EvidenceBundleContractError(ValueError):
    """Stable fail-closed error for unsafe or malformed evidence."""


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    opaque_reference: str
    kind: EvidenceKind
    text: str
    occurred_at: datetime | None
    axes: tuple[RetrievalAxis, ...]
    source_succeeded: bool = True
    observable: bool = True

    def __post_init__(self) -> None:
        if (
            not self.opaque_reference
            or len(self.opaque_reference) > 96
            or not self.text.strip()
            or len(self.text) > MAX_EVIDENCE_ITEM_CHARS
        ):
            raise EvidenceBundleContractError("evidence_item_shape_invalid")
        if not self.source_succeeded or not self.observable:
            raise EvidenceBundleContractError("evidence_item_untrusted")
        if not self.axes or len(set(self.axes)) != len(self.axes):
            raise EvidenceBundleContractError("evidence_item_axes_invalid")
        if self.occurred_at is not None and self.occurred_at.tzinfo is None:
            raise EvidenceBundleContractError("evidence_item_timezone_required")

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
    "compute_evidence_hash",
    "opaque_evidence_reference",
]
