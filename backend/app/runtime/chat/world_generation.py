"""Temporary historical names; actual Chat workflows live in domain services."""
from app.domains.chat.service.generation import RESPONSE_REQUEST_DEADLINE_SECONDS, RESPONSE_CONTEXT_MESSAGE_LIMIT, RESPONSE_CONTEXT_CHAR_LIMIT, _recent_context
from app.domains.chat.service.profiles import _response_profile as _profile
from app.domains.chat.service.evidence import _optional_datetime, _related_direction, _chat_source_label
from app.domains.chat.repository.response_requests import _active_request, _latest_request_row
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork, _character_labels
from app.runtime.chat.evidence_reads import world_character_name as _world_character_name
from app.runtime.chat.message_composition import generation_service, evidence_service

accept_world_message = generation_service.accept_world_message
retry_world_response = generation_service.retry_world_response
get_world_response_request = generation_service.get_world_response_request
get_latest_world_response_request = generation_service.get_latest_world_response_request
stream_world_response = generation_service.stream_world_response
_mutation_thread = generation_service._mutation_thread
_recover_if_expired = generation_service._recover_if_expired
_request_read = generation_service._request_read
_record_read = generation_service._record_read
_fail_before_workflow = generation_service._fail_before_workflow
_terminal_event = generation_service._terminal_event
_fence = generation_service._fence
_event = generation_service._event

get_world_response_evidence = evidence_service.get_world_response_evidence
_chat_evidence_item = evidence_service._chat_evidence_item

__all__ = ['RESPONSE_REQUEST_DEADLINE_SECONDS', 'SqlAlchemyResponseWorkflowUnitOfWork', 'accept_world_message', 'get_latest_world_response_request', 'get_world_response_request', 'retry_world_response', 'stream_world_response']
