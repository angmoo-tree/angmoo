"""Bounded interpretation data, separate from permissions and retrieval evidence."""
from dataclasses import dataclass, replace
import hashlib
import json

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError

HYBRID_ADMISSION_REVISION = "hybrid-admission.v1"


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RecallInterpretationContext:
    request_id: str
    intent_hash: str
    resolved_hash: str
    user_message_hash: str
    search_text: str | None
    mentions: tuple[tuple[str, str, str], ...]
    direction: tuple[str, str] | None
    time_expression: str | None
    time_status: str
    direction_status: str
    time_bounds: tuple[str, str] | None
    request_scope_hash: str | None = None
    evidence_hash: str | None = None
    revision: str = HYBRID_ADMISSION_REVISION

    def __post_init__(self):
        if (not isinstance(self.mentions, tuple) or any(not isinstance(row, tuple) or len(row) != 3 for row in self.mentions)
            or any(value is not None and not isinstance(value, tuple) for value in (self.direction, self.time_bounds))):
            raise RetrievalContractError("recall_interpretation_mutable_input")
        hashes = (self.intent_hash, self.resolved_hash, self.user_message_hash)
        if (not self.request_id or self.revision != HYBRID_ADMISSION_REVISION
            or any(len(x) != 64 or any(c not in "0123456789abcdef" for c in x) for x in hashes)
            or (self.request_scope_hash is None) != (self.evidence_hash is None)):
            raise RetrievalContractError("recall_interpretation_binding_invalid")
        for value in (self.request_scope_hash, self.evidence_hash):
            if value is not None and (len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
                raise RetrievalContractError("recall_interpretation_binding_invalid")
        if self.search_text is not None and (not self.search_text.strip() or len(self.search_text) > 4000):
            raise RetrievalContractError("recall_interpretation_query_invalid")
        if len(self.mentions) > 4 or any(
            len(ref) > 64 or not name.strip() or len(name) > 160
            or status not in {"resolved", "unmatched", "multiple", "unavailable"}
            for ref, name, status in self.mentions
        ):
            raise RetrievalContractError("recall_interpretation_mentions_invalid")
        if (self.time_status not in {"resolved", "ambiguous", "not_requested"}
            or self.direction_status not in {"resolved", "ambiguous", "not_requested"}
            or (self.time_expression is not None and len(self.time_expression) > 96)
            or (self.direction is not None and (len(self.direction) != 2 or any(len(x) > 64 for x in self.direction)))
            or (self.time_bounds is not None and (len(self.time_bounds) != 2 or any(len(x) > 40 for x in self.time_bounds)))):
            raise RetrievalContractError("recall_interpretation_conditions_invalid")
        if len(json.dumps(self.provider_payload(), ensure_ascii=False)) > 6500:
            raise RetrievalContractError("recall_interpretation_limit_exceeded")

    def freeze(self, evidence):
        if evidence.request_id != self.request_id:
            raise RetrievalContractError("recall_interpretation_request_mismatch")
        if self.evidence_hash is not None and (
            self.evidence_hash != evidence.evidence_hash or self.request_scope_hash != evidence.request_scope_hash
        ):
            raise RetrievalContractError("recall_interpretation_evidence_mismatch")
        return replace(self, request_scope_hash=evidence.request_scope_hash, evidence_hash=evidence.evidence_hash)

    def assert_routing(self, intent, resolved):
        if (self.request_id != resolved.request_id or self.intent_hash != intent.envelope_hash
            or self.resolved_hash != resolved.envelope_hash or self.search_text != intent.search_text
            or tuple((ref, name) for ref, name, _ in self.mentions) != tuple((e.ref, e.mention) for e in intent.entities)
            or self.direction != (None if intent.relationship is None else (intent.relationship.from_ref, intent.relationship.to_ref))
            or self.time_expression != (None if intent.time_scope is None else intent.time_scope.expression)
            or self.time_bounds != (None if resolved.absolute_time_from is None else (resolved.absolute_time_from, resolved.absolute_time_to))):
            raise RetrievalContractError("recall_interpretation_routing_mismatch")

    def assert_response(self, user_message, evidence):
        if (self.user_message_hash != text_hash(user_message) or self.request_id != evidence.request_id
            or self.request_scope_hash != evidence.request_scope_hash or self.evidence_hash != evidence.evidence_hash):
            raise RetrievalContractError("recall_interpretation_response_mismatch")

    def provider_payload(self):
        # Only original mentions and semantic aliases; never resolved IDs or lookup candidates.
        return {
            "revision": self.revision, "search_text": self.search_text,
            "mentions": [{"ref": ref, "mention": name, "resolution": status} for ref, name, status in self.mentions],
            "requested_direction": self.direction, "direction_resolution": self.direction_status,
            "time_expression": self.time_expression, "time_resolution": self.time_status,
            "applied_time_filter": self.time_bounds,
        }

    @property
    def content_hash(self):
        return text_hash(json.dumps({"binding": [self.request_id, self.intent_hash, self.resolved_hash,
            self.user_message_hash, self.request_scope_hash, self.evidence_hash],
            "data": self.provider_payload()}, ensure_ascii=True, sort_keys=True))

    def manifest(self):
        return {"revision": self.revision, "content_hash": self.content_hash,
            "unresolved_mentions": sum(status != "resolved" for _, _, status in self.mentions),
            "time_resolution": self.time_status, "direction_resolution": self.direction_status,
            "time_filter_applied": self.time_bounds is not None}
