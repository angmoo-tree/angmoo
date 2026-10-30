"""Typed, bounded request-owned input components. Never deserialize executable objects."""
import hashlib
from dataclasses import replace
from pydantic import TypeAdapter
from app.domains.chat.contracts.initial_input import _encoded, to_wire
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.routing_result import RetrievalRoutingResult

ROUTING_KEY = "_initial_routing"
CANONICAL_KEY = "_initial_canonical_result"
ROUTING_STARTED = "_initial_routing_started"
RETRIEVAL_STARTED = "_initial_retrieval_started"
RETRY_KEYS = (ROUTING_KEY, CANONICAL_KEY, ROUTING_STARTED, RETRIEVAL_STARTED)


def pack(value, kind, record):
    payload = to_wire(value)
    material = {"policy": "chat-input-component.v1", "slot": record.response_slot_id,
        "scope_hash": record.request_scope_hash, "payload": payload}
    return {**material, "digest": hashlib.sha256(_encoded(material)).hexdigest()}


def unpack(raw, kind, *, slot, scope_hash):
    try:
        if type(raw) is not dict or set(raw) != {"policy", "slot", "scope_hash", "payload", "digest"}:
            raise ValueError()
        material = {key: raw[key] for key in ("policy", "slot", "scope_hash", "payload")}
        if (material["policy"] != "chat-input-component.v1" or material["slot"] != slot
                or material["scope_hash"] != scope_hash
                or hashlib.sha256(_encoded(material)).hexdigest() != raw["digest"]):
            raise ValueError()
        return TypeAdapter(kind).validate_python(raw["payload"])
    except (TypeError, ValueError, KeyError) as exc:
        raise RetrievalContractError("chat_initial_component_invalid") from exc


def routing_for_request(raw, record):
    result = unpack(raw, RetrievalRoutingResult, slot=record.response_slot_id, scope_hash=record.request_scope_hash)
    resolved = replace(result.resolved, request_id=record.request_id)
    interpretation = None if result.interpretation is None else replace(result.interpretation,
        request_id=record.request_id, resolved_hash=resolved.envelope_hash)
    return replace(result, resolved=resolved, interpretation=interpretation)
