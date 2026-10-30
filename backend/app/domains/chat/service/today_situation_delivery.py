"""Bind selected Today prose to private event references without storage I/O."""
from app.domains.chat.contracts.evidence_bundle import EvidenceKind
from app.domains.chat.contracts.response_request import build_request_scope_hash
from app.domains.chat.exceptions import ChatSituationEvidenceError
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler


def selected_event_entries(command, bundle, payload, scope):
    selected = [(index, item) for index, item in enumerate(bundle.items)
        if item.kind is EvidenceKind.TODAY_SNS_ACTIVITY
        and item.locator is not None]
    if not selected:
        return {}
    today, request, preflight = command.today_sns_snapshot, command.request, command.preflight
    identity = (preflight.owner_id, preflight.world_id, preflight.responding_world_character_id)
    expected_hash = build_request_scope_hash(owner_id=preflight.owner_id, world_id=preflight.world_id,
        thread_id=preflight.thread_id, user_message_id=request.user_message_id,
        requester_world_character_id=preflight.requester_world_character_id,
        responding_world_character_id=preflight.responding_world_character_id)
    if (today is None or (today.owner_id, today.world_id, today.subject_world_character_id) != identity
            or (scope.owner_id, scope.world_id, scope.subject_world_character_id) != identity
            or request.thread_id != preflight.thread_id or request.request_scope_hash != expected_hash
            or bundle.request_id != request.request_id or bundle.request_scope_hash != expected_hash):
        raise ChatSituationEvidenceError("situation_today_scope_invalid")
    if payload.get("frozen_evidence") != bundle.provider_payload():
        raise ChatSituationEvidenceError("situation_today_payload_invalid")
    return {index: EvidenceBundleAssembler.today_event_entry(item, today) for index, item in selected}
