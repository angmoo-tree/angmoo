"""Bounded reference content for one admitted response slot; no credentials."""
from dataclasses import dataclass, replace, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Literal
import hashlib
import json
from collections.abc import Mapping

from pydantic import TypeAdapter
from app.domains.chat.contracts.character_response_generator import CharacterResponseProfile, CharacterResponseContextMessage
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterContextMessage
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivitySnapshot
from app.domains.chat.contracts.image_evidence import ChatImageEvidence
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext
from app.domains.relationships.contracts.social_context import SocialContextSnapshot
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError

INPUT_KEY = '_initial_reference_input'
INPUT_POLICY = 'chat-initial-input.v1'
MAX_INPUT_BYTES = 512 * 1024
UNAVAILABLE_KEY = '_initial_reference_unavailable'


def assert_available(state):
    """An acquired input cannot be replaced by a later live lookup after loss."""
    acquired = ('_initial_routing_started', '_initial_routing',
        '_initial_retrieval_started', '_initial_canonical_result',
        'intent_hash', 'resolved_hash', 'social_snapshot', 'router_diagnostic')
    if state.get(UNAVAILABLE_KEY) or (INPUT_KEY not in state and any(state.get(key) for key in acquired)):
        raise RetrievalContractError('chat_initial_input_unavailable')


@dataclass(frozen=True)
class InitialReferenceInput:
    policy: Literal['chat-initial-input.v1']
    request_scope_hash: str
    response_slot_id: str
    scope: tuple[str, str, str, str, str]
    user_message: str
    image_context: str | None
    profile: CharacterResponseProfile
    router_context: tuple[RetrievalRouterContextMessage, ...]
    response_context: tuple[CharacterResponseContextMessage, ...]
    character_labels: dict[str, str]
    today_sns_snapshot: TodaySnsActivitySnapshot | None
    social_snapshot: SocialContextSnapshot | None
    image_evidence: ChatImageEvidence | None
    chat_identity: ChatIdentityContext | None


_ADAPTER = TypeAdapter(InitialReferenceInput)


def _scope(command):
    p = command.preflight
    return (p.owner_id, p.world_id, p.thread_id, p.requester_world_character_id, p.responding_world_character_id)


def _encoded(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_INPUT_BYTES:
        raise RetrievalContractError('chat_initial_input_limit')
    return raw


def to_wire(value):
    """JSON values for immutable DTOs, including their read-only mapping fields."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_wire(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_wire(item) for item in value]
    if isinstance(value, Enum):
        return to_wire(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("chat_initial_input_type_invalid")


def capture(command):
    value = InitialReferenceInput(INPUT_POLICY, command.request.request_scope_hash,
        command.request.response_slot_id, _scope(command), command.preflight.user_message,
        command.preflight.image_context, command.profile, command.router_context,
        command.response_context, dict(command.character_labels), command.today_sns_snapshot,
        command.social_snapshot, command.image_evidence, command.chat_identity)
    payload = to_wire(value)
    raw = _encoded(payload)
    return {'payload': payload, 'digest': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def read(raw, *, request_scope_hash, response_slot_id, scope):
    try:
        if type(raw) is not dict or set(raw) != {'payload', 'digest', 'bytes'}:
            raise ValueError()
        encoded = _encoded(raw['payload'])
        if raw['digest'] != hashlib.sha256(encoded).hexdigest() or raw['bytes'] != len(encoded):
            raise ValueError()
        value = _ADAPTER.validate_python(raw['payload'])
        if (value.request_scope_hash, value.response_slot_id, value.scope) != (
                request_scope_hash, response_slot_id, tuple(scope)):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise RetrievalContractError('chat_initial_input_invalid') from exc


def restore(command, raw):
    value = read(raw, request_scope_hash=command.request.request_scope_hash,
        response_slot_id=command.request.response_slot_id, scope=_scope(command))
    return replace(command, preflight=replace(command.preflight,
        user_message=value.user_message, image_context=value.image_context),
        **{name: getattr(value, name) for name in ('profile', 'router_context', 'response_context',
            'character_labels', 'today_sns_snapshot', 'social_snapshot', 'image_evidence', 'chat_identity')})
