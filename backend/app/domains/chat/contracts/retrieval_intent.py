"""Strict semantic output owned by the P8-L Retrieval Router.

The Router may describe meaning, but it never owns canonical identifiers,
permissions, database operations, or execution caps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import Any
from app.domains.chat.contracts.reference_observation import reference_failure
from app.domains.relationships.contracts.graph_requirements import GraphQueryRequirement, validate_graph_queries


RETRIEVAL_INTENT_VERSION = "retrieval-intent.v1"
RETRIEVAL_ACTIVITY_KINDS = frozenset({"posts_authored", "replies_authored", "replies_received",
    "mentions_received", "reactions_given", "reactions_received", "reposts", "follows"})
_REF_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class RetrievalContractError(ValueError):
    """Stable fail-closed error for malformed retrieval contracts."""


class RetrievalDecision(StrEnum):
    RETRIEVAL = "RETRIEVAL"
    CURRENT_CONTEXT = "CURRENT_CONTEXT"
    CLARIFICATION = "CLARIFICATION"


class RetrievalRoute(StrEnum):
    CURRENT_CONTEXT = "CURRENT_CONTEXT"
    CANONICAL = "CANONICAL"
    GRAPH = "GRAPH"
    BOTH = "BOTH"
    CLARIFICATION = "CLARIFICATION"


class RetrievalTimeKind(StrEnum):
    CURRENT_DAY = "current_day"
    HISTORICAL_UNSPECIFIED = "historical_unspecified"
    RECENT = "recent"
    RELATIVE = "relative"
    ABSOLUTE_RANGE = "absolute_range"


class RetrievalAggregationKind(StrEnum):
    COUNT = "count"
    RANK = "rank"
    COMPARE = "compare"
    GROUP = "group"


@dataclass(frozen=True, slots=True)
class RetrievalEntityMention:
    ref: str
    mention: str
    role: str

    def __post_init__(self) -> None:
        if not _REF_RE.fullmatch(self.ref):
            reference_failure("entity_ref", self.ref, rule="entity_ref_format.v1", reason="ref_format_invalid")
            raise RetrievalContractError("retrieval_intent_entity_ref_invalid")
        if not self.mention.strip() or len(self.mention) > 160:
            raise RetrievalContractError("retrieval_intent_entity_mention_invalid")
        if not self.role.strip() or len(self.role) > 64:
            raise RetrievalContractError("retrieval_intent_entity_role_invalid")

    def payload(self) -> dict[str, str]:
        return {"ref": self.ref, "mention": self.mention, "role": self.role}


@dataclass(frozen=True, slots=True)
class RetrievalRelationshipMeaning:
    from_ref: str
    to_ref: str
    dimension: str | None = None
    requested_polarity: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (("relationship_from", self.from_ref), ("relationship_to", self.to_ref)):
            if value not in {"requester_character", "responding_character"} and not _REF_RE.fullmatch(value):
                reference_failure(field_name, value, rule="relationship_ref_format.v1", reason="ref_format_invalid")
                raise RetrievalContractError("retrieval_intent_relationship_ref_invalid")
        if self.from_ref == self.to_ref:
            reference_failure("relationship", self.from_ref, rule="relationship_pair.v1", reason="same_endpoint", related=self.to_ref)
            raise RetrievalContractError("retrieval_intent_relationship_self_invalid")

    def payload(self) -> dict[str, str | None]:
        return {
            "from": self.from_ref,
            "to": self.to_ref,
            "dimension": self.dimension,
            "requested_polarity": self.requested_polarity,
        }


@dataclass(frozen=True, slots=True)
class RetrievalTimeMeaning:
    kind: RetrievalTimeKind
    expression: str | None = None
    unit: str | None = None
    offset: int | None = None
    period: str | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        if self.unit is not None:
            if self.unit not in {"day", "week", "month"} or type(self.offset) is not int or not -366 <= self.offset <= 0:
                raise RetrievalContractError("retrieval_intent_time_meaning_invalid")
            if self.kind is not RetrievalTimeKind.RELATIVE or self.period not in {None, "morning"} or (self.period and self.unit != "day"):
                raise RetrievalContractError("retrieval_intent_time_meaning_invalid")
        elif self.offset is not None or self.period is not None:
            raise RetrievalContractError("retrieval_intent_time_meaning_invalid")
        if self.timezone is not None:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(self.timezone)
            except (TypeError, ValueError, ZoneInfoNotFoundError):
                raise RetrievalContractError("retrieval_intent_time_meaning_invalid") from None
        if self.expression is not None and (
            not self.expression.strip() or len(self.expression) > 96
        ):
            raise RetrievalContractError("retrieval_intent_time_expression_invalid")
        if self.kind in {
            RetrievalTimeKind.RELATIVE,
            RetrievalTimeKind.ABSOLUTE_RANGE,
        } and self.expression is None and self.unit is None:
            raise RetrievalContractError("retrieval_intent_time_expression_required")

    def payload(self) -> dict[str, str | None]:
        payload = {"kind": self.kind.value, "expression": self.expression}
        if self.unit is not None or self.timezone is not None:
            payload.update(unit=self.unit, offset=self.offset, period=self.period, timezone=self.timezone)
        return payload


@dataclass(frozen=True, slots=True)
class RetrievalAggregationMeaning:
    kind: RetrievalAggregationKind
    target_role: str

    def __post_init__(self) -> None:
        if not self.target_role.strip() or len(self.target_role) > 64:
            raise RetrievalContractError("retrieval_intent_aggregation_target_invalid")

    def payload(self) -> dict[str, str]:
        return {"kind": self.kind.value, "target_role": self.target_role}


@dataclass(frozen=True, slots=True)
class RetrievalIntentEnvelope:
    decision: RetrievalDecision
    route: RetrievalRoute
    intent: str
    entities: tuple[RetrievalEntityMention, ...] = ()
    relationship: RetrievalRelationshipMeaning | None = None
    time_scope: RetrievalTimeMeaning | None = None
    aggregation: RetrievalAggregationMeaning | None = None
    coordination_hint: str | None = None
    clarification_slot: str | None = None
    version: str = RETRIEVAL_INTENT_VERSION
    # Code-owned provenance, not part of the model wire payload or semantic hash.
    coordination_source: str = "model"
    graph_queries: tuple[GraphQueryRequirement, ...] = ()
    search_text: str | None = None
    activity_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (not isinstance(self.activity_kinds, tuple) or len(self.activity_kinds) > 8
            or any(type(kind) is not str or kind not in RETRIEVAL_ACTIVITY_KINDS for kind in self.activity_kinds)
            or len(set(self.activity_kinds)) != len(self.activity_kinds)):
            raise RetrievalContractError("retrieval_activity_kinds_invalid")
        if self.search_text is not None and (self.route is not RetrievalRoute.CANONICAL
            or not isinstance(self.search_text, str) or not self.search_text.strip() or len(self.search_text) > 4000):
            raise RetrievalContractError("retrieval_search_text_invalid")
        if self.coordination_source not in {"model", "code"}:
            raise RetrievalContractError("retrieval_intent_coordination_source_invalid")
        if self.version not in {RETRIEVAL_INTENT_VERSION, "retrieval-intent.v2"}:
            raise RetrievalContractError("retrieval_intent_version_mismatch")
        if self.graph_queries:
            if self.version != "retrieval-intent.v2":
                raise RetrievalContractError("retrieval_intent_version_mismatch")
            validate_graph_queries(self.graph_queries, {e.ref for e in self.entities} | {"builtin-requester"})
        if not self.intent.strip() or len(self.intent) > 96:
            raise RetrievalContractError("retrieval_intent_name_invalid")
        if len(self.entities) > 4:
            raise RetrievalContractError("retrieval_intent_entity_limit_exceeded")
        refs = [entity.ref for entity in self.entities]
        if len(refs) != len(set(refs)):
            raise RetrievalContractError("retrieval_intent_entity_ref_duplicate")
        if self.route is RetrievalRoute.CURRENT_CONTEXT:
            expected = RetrievalDecision.CURRENT_CONTEXT
        elif self.route is RetrievalRoute.CLARIFICATION:
            expected = RetrievalDecision.CLARIFICATION
        else:
            expected = RetrievalDecision.RETRIEVAL
        if self.decision is not expected:
            raise RetrievalContractError("retrieval_intent_decision_route_mismatch")
        if self.relationship is not None:
            allowed = set(refs) | {"requester_character", "responding_character"}
            if (
                self.relationship.from_ref not in allowed
                or self.relationship.to_ref not in allowed
            ):
                reference_failure("relationship", self.relationship.from_ref, rule="relationship_bound.v1", reason="unbound", related=self.relationship.to_ref, declared=allowed)
                raise RetrievalContractError("retrieval_intent_relationship_unbound")
        if self.route is RetrievalRoute.CLARIFICATION and not self.clarification_slot:
            raise RetrievalContractError("retrieval_intent_clarification_slot_required")

    def payload(self) -> dict[str, Any]:
        return {
            **({"activity_kinds": list(self.activity_kinds)} if self.activity_kinds else {}),
            **({"search_text": self.search_text} if self.search_text is not None else {}),
            **({"graph_queries": [q.payload() for q in self.graph_queries]} if self.version == "retrieval-intent.v2" else {}),
            "version": self.version,
            "decision": self.decision.value,
            "route": self.route.value,
            "intent": self.intent,
            "entities": [entity.payload() for entity in self.entities],
            "relationship": (
                None if self.relationship is None else self.relationship.payload()
            ),
            "time_scope": (
                None if self.time_scope is None else self.time_scope.payload()
            ),
            "aggregation": (
                None if self.aggregation is None else self.aggregation.payload()
            ),
            "coordination_hint": self.coordination_hint,
            "clarification_slot": self.clarification_slot,
        }

    @property
    def envelope_hash(self) -> str:
        encoded = json.dumps(
            self.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "RETRIEVAL_INTENT_VERSION",
    "RetrievalContractError",
    "RetrievalAggregationKind",
    "RetrievalAggregationMeaning",
    "RetrievalDecision",
    "RetrievalEntityMention",
    "RetrievalIntentEnvelope",
    "RetrievalRelationshipMeaning",
    "RetrievalRoute",
    "RetrievalTimeKind",
    "RetrievalTimeMeaning",
]
