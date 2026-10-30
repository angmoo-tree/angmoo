"""Durable generation admission, replay, status and terminal failure rules."""

from __future__ import annotations
from app.contracts.name_binding import NameBindingError
from app.contracts.environment import EnvironmentSnapshot
from app.domains.identity.service.environment import lock_environment_admission, snapshot
from app.core.database_transactions import database_write, postgres_db_unit
from app.core.async_session import session_call
import asyncio
import json

from app.domains.chat.service.message_pages import committed_evidence_summary
from app.domains.chat.service.diagnostic_capture import capture
from app.domains.chat.service.db_observation import observe_admission, observe_generation
from app.core.session_write_observation import finish_session
from app.core.work_observation import contextual

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.domains.characters.service.profile import (
    get_character as get_responding_character,
)
from app.domains.chat import models, schemas
from app.domains.chat.contracts import (
    CHAT_GENERATION_STREAM_VERSION,
    TERMINAL_STATES,
    CharacterResponseContextMessage,
    CreateResponseRequest,
    GenerationEvent,
    GenerationEventType,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
    RetrievalPreflightCommand,
    RetrievalRouterContextMessage,
    build_request_scope_hash,
)
from app.domains.chat.contracts.context import ChatUser
from app.domains.chat.contracts.execution import GenerationWorkflows
from app.domains.chat.exceptions import (
    MessageCredentialInvalidError,
    MessageCredentialRequiredError,
    MessageInFlightError,
    MessageNotFoundError,
    MessageValidationError,
)
from app.domains.chat.repository import response_requests as request_repository
from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.domains.chat.service import profiles
from app.domains.chat.service.response_workflow import ResponseWorkflowCommand
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.domains.chat.service.today_sns_activity import TodaySnsActivityAssembler
from app.domains.identity.contracts import CredentialMaterial
from app.domains.memory.service.recall import CanonicalRecallService
from app.domains.worlds.service.character_entry import get_character_entry_world
from app.domains.world_characters.contracts.configuration import configuration_from_request
from app.domains.world_characters.service.configuration import configuration_for_actor
from app.domains.chat.contracts.supervisor_selection import (
    NAME_SELECTION_PROTOCOL, ADVISORY_SELECTION_PROTOCOL, SELECTION_PROTOCOL_KEY, read_selection_protocol,
)
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.temporal_recall import ChatTimeContext, TIME_CONTEXT_KEY, TEMPORAL_SELECTION_PROTOCOL

RESPONSE_REQUEST_DEADLINE_SECONDS = 180
RESPONSE_CONTEXT_MESSAGE_LIMIT = 20
RESPONSE_CONTEXT_CHAR_LIMIT = 8_000

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(
        self,
        thread_service: ThreadService,
        settings_service: MessageSettingsService,
        workflows: GenerationWorkflows,
        images=None,
        memory_policy=None,
    ) -> None:
        self.thread_service = thread_service
        self.settings_service = settings_service
        self.workflows = workflows
        self.images = images
        self.memory_policy = memory_policy

    @observe_admission
    def accept_world_message(
        self, db, user, world_id, thread_id, data,
    ) -> schemas.WorldChatMessageAcceptRead:
        bind = db.get_bind()
        if (bind.dialect.name == "postgresql" and isinstance(bind, Engine)
                and not data.attachment_asset_id):
            # This unit mutates one locked thread and its message/request; first
            # memory-policy initialization has its own existing scope row fence.
            # The thread's MVCC fence owns active-request/idempotency decisions; shared
            # owner/World/role/environment fences retain revocation semantics.
            # A stable snapshot avoids unrelated threads' SSI predicate conflicts.
            # Images/retries can reserve cross-thread quotas and keep SERIALIZABLE.
            result = database_write(db,
                lambda: self._accept_world_message(db, user, world_id, thread_id, data),
                postgres_isolation="REPEATABLE READ")
        else:
            result = self._accept_world_message(db, user, world_id, thread_id, data)
        if result.outcome == "accepted":
            capture.admit((user.id, world_id, thread_id), result.response_request.request_id)
        return result

    @postgres_db_unit
    def _accept_world_message(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        data: schemas.WorldChatMessageCreate,
    ) -> schemas.WorldChatMessageAcceptRead:
        thread = self._mutation_thread(db, user, world_id, thread_id, admission=True)
        content = data.content.strip()
        if not content and not data.attachment_asset_id:
            raise MessageValidationError("메시지 내용을 입력해 주세요.")
        idempotency_key = data.idempotency_key.strip()
        if len(idempotency_key) < 16:
            raise MessageValidationError("message_idempotency_key_invalid")
        existing = db.scalar(
            select(models.ChatResponseRequest).where(
                models.ChatResponseRequest.thread_id == thread.id,
                models.ChatResponseRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            message = db.get(models.MessageMessage, existing.user_message_id)
            existing_asset = self.images.existing_asset(db, message.id) if self.images and message else None
            if message is None or message.content != content or existing_asset != data.attachment_asset_id:
                raise MessageValidationError("message_idempotency_conflict")
            return schemas.WorldChatMessageAcceptRead(
                outcome="replayed",
                user_message=schemas.MessageMessageRead.model_validate(message),
                response_request=self._request_read(db, existing),
            )
        if request_repository._active_request(db, thread.id) is not None:
            raise MessageInFlightError("이미 답장을 만들고 있어요.")
        request_metadata = self._request_names(db, user, thread)
        selected_model = self.thread_service.resolve_world_thread_response_model(db, user, thread)
        now = datetime.now(UTC)
        if request_metadata.get(SELECTION_PROTOCOL_KEY) == TEMPORAL_SELECTION_PROTOCOL:
            request_metadata[TIME_CONTEXT_KEY] = ChatTimeContext.create(now,
                EnvironmentSnapshot.from_dict(request_metadata["_environment"]).timezone).payload()
        message = models.MessageMessage(
            thread_id=thread.id, role="user", content=content, model=None, status="ok", created_at=now
        )
        db.add(message)
        db.flush()
        if data.attachment_asset_id:
            if self.images is None:
                raise MessageValidationError("image_runtime_unavailable")
            self.images.accept(db, user.id, thread.id, message.id, data.attachment_asset_id)
        thread.last_message_at = now
        request_id = f"request-{uuid4().hex}"
        generation_id = f"generation-{uuid4().hex}"
        response_slot_id = f"response-{uuid4().hex}"
        scope_hash = build_request_scope_hash(
            owner_id=user.id,
            world_id=world_id,
            thread_id=thread.id,
            user_message_id=message.id,
            requester_world_character_id=thread.requester_world_character_id or "",
            responding_world_character_id=thread.responding_world_character_id or "",
        )
        lifecycle = SqlAlchemyResponseLifecycleRepository(db)
        record = lifecycle.accept(
            CreateResponseRequest(
                request_id=request_id,
                thread_id=thread.id,
                user_message_id=message.id,
                response_slot_id=response_slot_id,
                request_scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                generation_id=generation_id,
                attempt_number=1,
                selected_model=selected_model,
                selected_thinking_level=thread.selected_thinking_level,
                deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
                request_metadata=request_metadata,
            )
        )
        finish_session(db)
        db.refresh(message)
        return schemas.WorldChatMessageAcceptRead(
            outcome="accepted",
            user_message=schemas.MessageMessageRead.model_validate(message),
            response_request=self._record_read(db, record),
        )

    @observe_admission
    def retry_world_response(
        self, db, user, world_id, thread_id, data,
    ) -> schemas.WorldChatMessageAcceptRead:
        result = self._retry_world_response(db, user, world_id, thread_id, data)
        if result.outcome == "accepted":
            capture.admit((user.id, world_id, thread_id), result.response_request.request_id)
        return result

    @postgres_db_unit
    def _retry_world_response(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        data: schemas.WorldChatRetryCreate,
    ) -> schemas.WorldChatMessageAcceptRead:
        thread = self._mutation_thread(db, user, world_id, thread_id, admission=True)
        idempotency_key = data.idempotency_key.strip()
        existing = db.scalar(
            select(models.ChatResponseRequest).where(
                models.ChatResponseRequest.thread_id == thread.id,
                models.ChatResponseRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            original = db.get(models.ChatResponseRequest, existing.retry_of_request_id)
            inherited_exclusion = bool(original and json.loads(original.node_state_json).get("_image_excluded"))
            if existing.retry_of_request_id != data.failed_request_id or bool(json.loads(existing.node_state_json).get("_image_excluded")) != (data.exclude_attachment or inherited_exclusion):
                raise MessageValidationError("retry_idempotency_conflict")
            message = db.get(models.MessageMessage, existing.user_message_id)
            if message is None:
                raise MessageNotFoundError("원래 메시지를 찾을 수 없습니다.")
            return schemas.WorldChatMessageAcceptRead(
                outcome="replayed",
                user_message=schemas.MessageMessageRead.model_validate(message),
                response_request=self._request_read(db, existing),
            )
        prior = db.get(models.ChatResponseRequest, data.failed_request_id)
        latest = request_repository._latest_request_row(db, thread.id)
        if prior is None or prior.thread_id != thread.id or latest is None:
            raise MessageNotFoundError("다시 시도할 응답을 찾을 수 없습니다.")
        if latest.request_id != prior.request_id:
            raise MessageValidationError("latest_retryable_response_required")
        if (
            prior.state not in {state.value for state in TERMINAL_STATES}
            or not prior.retryable
            or prior.committed_assistant_message_id is not None
        ):
            raise MessageValidationError("response_not_retryable")
        if request_repository._active_request(db, thread.id) is not None:
            raise MessageInFlightError("이미 답장을 만들고 있어요.")
        message = db.get(models.MessageMessage, prior.user_message_id)
        if message is None or message.role != "user":
            raise MessageNotFoundError("원래 메시지를 찾을 수 없습니다.")
        later_user_message = db.scalar(
            select(models.MessageMessage.id)
            .where(
                models.MessageMessage.thread_id == thread.id,
                models.MessageMessage.role == "user",
                models.MessageMessage.id > message.id,
            )
            .limit(1)
        )
        if later_user_message is not None:
            raise MessageValidationError("latest_retryable_response_required")
        prior_metadata = json.loads(prior.node_state_json)
        prior_protocol = read_selection_protocol(prior_metadata)
        self._validate_request_names(db, user, thread, SqlAlchemyResponseLifecycleRepository(db).get_request(prior.request_id))
        # Retry the admitted input, including historical namespaces. Current
        # World edits must not replace a saved name or introduce a new snapshot.
        from app.domains.chat.contracts.input_receipt import RETRY_KEYS, ROUTING_KEY, ROUTING_STARTED
        retry_metadata = {key: prior_metadata[key] for key in ("name_binding_policy", "name_binding", "_world_credential", "chat_identity_context.v1", "_situation_policy", "_initial_reference_input", *RETRY_KEYS)
            if key in prior_metadata}
        from app.domains.chat.contracts.initial_input import UNAVAILABLE_KEY, assert_available
        try:
            assert_available(prior_metadata)
        except RetrievalContractError:
            # Preserve the loss even when old-policy diagnostics are not copied
            # to the new attempt. The admitted attempt terminates without AI.
            retry_metadata[UNAVAILABLE_KEY] = True
        # An explicitly rejected Router output acquired no reference result.
        # A user retry may interpret the same saved input again. An interrupted
        # or missing committed result remains ambiguous and must fail closed.
        diagnostic = prior_metadata.get("router_diagnostic")
        if (prior_metadata.get("failure_class") == "router_schema_rejected"
                and isinstance(diagnostic, dict) and diagnostic.get("repair_exhausted") is True
                and ROUTING_KEY not in prior_metadata and "_initial_reference_input" in prior_metadata):
            retry_metadata[ROUTING_STARTED] = False
        if prior_protocol is not None:
            retry_metadata[SELECTION_PROTOCOL_KEY] = prior_protocol
        if prior_protocol == TEMPORAL_SELECTION_PROTOCOL:
            context = ChatTimeContext.read(prior_metadata.get(TIME_CONTEXT_KEY))
            original_time = message.created_at.replace(tzinfo=UTC) if message.created_at.tzinfo is None else message.created_at
            if (context.instant != original_time or context.timezone !=
                EnvironmentSnapshot.from_dict(prior_metadata["_environment"]).timezone):
                raise MessageValidationError("chat_time_context_binding_invalid")
            retry_metadata[TIME_CONTEXT_KEY] = context.payload()
        elif (settings.CHAT_RECALL_MODE == "social_hybrid" and "chat_identity_context.v1" in prior_metadata
              and "_environment" in prior_metadata and message.created_at is not None):
            # An explicit retry can adopt v4 only from the admitted original input.
            original_time = message.created_at.replace(tzinfo=UTC) if message.created_at.tzinfo is None else message.created_at
            context = ChatTimeContext.create(original_time, EnvironmentSnapshot.from_dict(prior_metadata["_environment"]).timezone)
            retry_metadata.update({SELECTION_PROTOCOL_KEY: TEMPORAL_SELECTION_PROTOCOL, TIME_CONTEXT_KEY: context.payload()})
        if "_world_configuration" in prior_metadata:
            self._request_configuration(thread, prior_metadata)
            retry_metadata["_world_configuration"] = prior_metadata["_world_configuration"]
        exclude_image = data.exclude_attachment or bool(prior_metadata.get("_image_excluded"))
        if data.exclude_attachment and not prior_metadata.get("_image_excluded"):
            if (prior_metadata.get("failure_class") != "image_interpretation_unavailable"
                or not message.content.strip() or self.images is None
                or self.images.existing_asset(db, message.id) is None):
                raise MessageValidationError("image_text_only_recovery_unavailable")
        if self.images and not exclude_image:
            self.images.reserve_retry(db, user.id, thread.id, message.id)
        selected_model = prior.selected_model
        selected_thinking_level = prior.selected_thinking_level
        now = datetime.now(UTC)
        record = SqlAlchemyResponseLifecycleRepository(db).accept(
            CreateResponseRequest(
                request_id=f"request-{uuid4().hex}",
                thread_id=thread.id,
                user_message_id=prior.user_message_id,
                response_slot_id=prior.response_slot_id,
                request_scope_hash=prior.request_scope_hash,
                idempotency_key=idempotency_key,
                generation_id=f"generation-{uuid4().hex}",
                attempt_number=prior.attempt_number + 1,
                retry_of_request_id=prior.request_id,
                selected_model=selected_model,
                selected_thinking_level=selected_thinking_level,
                deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
                request_metadata={**retry_metadata,
                    "_environment": json.loads(prior.node_state_json).get("_environment", snapshot(db, user.id).to_dict()),
                    "_image_excluded": exclude_image},
            )
        )
        finish_session(db)
        capture.admit((user.id, world_id, thread_id), record.request_id)
        return schemas.WorldChatMessageAcceptRead(
            outcome="accepted",
            user_message=schemas.MessageMessageRead.model_validate(message),
            response_request=self._record_read(db, record),
        )

    def get_world_response_request(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        request_id: str,
    ) -> schemas.WorldChatGenerationRequestRead:
        self._read_thread(db, user, world_id, thread_id)
        row = db.get(models.ChatResponseRequest, request_id)
        if row is None or row.thread_id != thread_id:
            raise MessageNotFoundError("응답 요청을 찾을 수 없습니다.")
        record = self._recover_if_expired(
            db, SqlAlchemyResponseLifecycleRepository(db).get_request(row.request_id)
        )
        return self._record_read(db, record)

    def get_latest_world_response_request(
        self, db: Session, user: ChatUser, world_id: str, thread_id: str
    ) -> schemas.WorldChatLatestRequestRead:
        self._read_thread(db, user, world_id, thread_id)
        row = request_repository._latest_request_row(db, thread_id)
        record = (
            None
            if row is None
            else self._recover_if_expired(
                db,
                SqlAlchemyResponseLifecycleRepository(db).get_request(row.request_id),
            )
        )
        return schemas.WorldChatLatestRequestRead(
            response_request=None if record is None else self._record_read(db, record)
        )

    def _read_thread(self, db, user, world_id, thread_id):
        self.thread_service._require_world_chat_owner_scope(db, user.id, world_id)
        thread = self.thread_service._get_owned_world_thread(db, user, world_id, thread_id)
        self.thread_service._world_thread_read(db, thread, include_messages=False)
        return thread

    def _mutation_thread(
        self, db: Session, user: ChatUser, world_id: str, thread_id: str, *, admission=False
    ) -> models.MessageThread:
        # Accepted requests already own an immutable environment snapshot.
        # Revalidation needs thread/scope fences, not a global admission write.
        if admission:
            lock_environment_admission(db, user.id)
        # Acquire installation scope before thread in both admission and
        # validation, so concurrent admission cannot invert the lock order.
        self.thread_service._require_world_chat_owner_scope(db, user.id, world_id, lock_scope=True)
        # Serialize admission with model PATCH before taking its model snapshot.
        thread = self.thread_service._get_owned_world_thread(
            db, user, world_id, thread_id, lock_thread=True, advance_admission=admission
        )
        # Admission needs the same participant/owner/block checks, not a UI DTO.
        # Reading the latest message here adds an unrelated SERIALIZABLE read
        # dependency immediately before INSERT (relation-wide on small tables).
        self.thread_service._world_thread_participants(db, thread, lock_scope=True)
        return thread

    def _request_names(self, db, user, thread):
        configuration = configuration_for_actor(db, character_id=thread.character_id, world_id=thread.world_id)
        if configuration is None or configuration.world_character_id != thread.responding_world_character_id:
            raise MessageValidationError("world_configuration_missing")
        metadata = {**self.workflows.capture_names(db, owner_id=user.id, world_id=thread.world_id,
            actor_id=thread.responding_world_character_id, requester_id=thread.requester_world_character_id),
            "_environment": snapshot(db, user.id).to_dict()}
        metadata["_world_configuration"] = configuration.request_snapshot()
        from app.contracts.name_binding import read_name_binding
        from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext, IDENTITY_KEY
        metadata[IDENTITY_KEY] = ChatIdentityContext.from_binding(read_name_binding(metadata), thread.id).to_dict()
        metadata["_world_credential"] = self.workflows.capture_credential(db, owner_id=user.id,
            world_id=thread.world_id, actor_id=thread.responding_world_character_id)
        metadata["_situation_policy"] = self.memory_policy(db, owner_id=user.id,
            world_id=thread.world_id, actor_id=thread.responding_world_character_id,
            environment=EnvironmentSnapshot.from_dict(metadata["_environment"])) if self.memory_policy else None
        if settings.CHAT_RECALL_MODE == "social_hybrid":
            metadata[SELECTION_PROTOCOL_KEY] = TEMPORAL_SELECTION_PROTOCOL
        return metadata

    def _request_configuration(self, thread, metadata):
        if "_world_configuration" not in metadata:
            # Historical accepted requests retain their existing input path.
            # A read or retry does not fabricate a new settings revision.
            return None
        try:
            configuration = configuration_from_request(metadata["_world_configuration"])
            if (configuration.world_id, configuration.world_character_id, configuration.character_id) != (
                thread.world_id, thread.responding_world_character_id, thread.character_id
            ):
                raise ValueError("world_configuration_snapshot_scope_invalid")
            return configuration
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise MessageValidationError("world_configuration_snapshot_invalid") from exc

    @contextual(chat_stage="cancel_or_failure")
    def _recover_if_expired(self, db: Session, record):
        now = datetime.now(UTC)
        if record.state in TERMINAL_STATES or record.deadline_at > now:
            return record
        repository = SqlAlchemyResponseLifecycleRepository(db)
        repository.recover_expired_requests(now=now, limit=100)
        finish_session(db)
        return repository.get_request(record.request_id)

    def _request_read(
        self, db: Session, row: models.ChatResponseRequest
    ) -> schemas.WorldChatGenerationRequestRead:
        return self._record_read(
            db, SqlAlchemyResponseLifecycleRepository(db).get_request(row.request_id)
        )

    def _record_read(
        self, db: Session, record
    ) -> schemas.WorldChatGenerationRequestRead:
        user_message = db.get(models.MessageMessage, record.user_message_id)
        if user_message is None:
            raise MessageNotFoundError("원래 메시지를 찾을 수 없습니다.")
        assistant = (
            None
            if record.committed_assistant_message_id is None
            else db.get(models.MessageMessage, record.committed_assistant_message_id)
        )
        image_state = self.images.state(db, user_message, record) if self.images else "none"
        return schemas.WorldChatGenerationRequestRead(
            request_id=record.request_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            response_slot_id=record.response_slot_id,
            state=record.state.value,
            route=None if record.route is None else record.route.value,
            retryable=record.retryable,
            failure_class=record.node_state.get("failure_class")
            or (
                None if record.terminal_reason is None else record.terminal_reason.value
            ),
            last_accepted_sequence=record.last_emitted_sequence,
            image_analysis_state=image_state,
            can_retry_without_image=image_state == "failed" and bool(user_message.content.strip()) and record.retryable,
            user_message=schemas.MessageMessageRead.model_validate(user_message),
            assistant_message=None
            if assistant is None
            else schemas.MessageMessageRead.model_validate(assistant),
            evidence_summary=committed_evidence_summary(record.request_id, assistant.id, record.response_metadata)
                if assistant is not None and record.state.value == "committed" else None,
            response_metadata={
                key: value
                for key, value in record.response_metadata.items()
                if not key.startswith("_")
            },
        )

    @contextual(chat_stage="cancel_or_failure")
    async def _fail_before_workflow(
        self,
        db: Session,
        record,
        *,
        failure_class: str,
        retryable: bool,
        reason: ResponseTerminalReason,
    ) -> AsyncIterator[GenerationEvent]:
        events = await session_call(db, lambda: self._persist_pre_workflow_failure(db, record,
            failure_class=failure_class, retryable=retryable, reason=reason))
        for event in events:
            yield event

    @postgres_db_unit
    def _persist_pre_workflow_failure(self, db, record, *, failure_class, retryable, reason):
        lifecycle = SqlAlchemyResponseLifecycleRepository(db)
        record = lifecycle.get_request(record.request_id)
        if record.state in TERMINAL_STATES:
            return (self._terminal_event(record),)
        now = datetime.now(UTC)
        record = lifecycle.acquire_lease(
            request_id=record.request_id,
            lease_token=f"lease-{uuid4().hex}",
            now=now,
            lease_expires_at=min(record.deadline_at, now + timedelta(seconds=30)),
        )
        finish_session(db)
        fence = self._fence(record)
        accepted = self._event(record, GenerationEventType.ACCEPTED, 0)
        lifecycle.accept_event(fence, accepted, now=datetime.now(UTC))
        finish_session(db)
        record = SqlAlchemyResponseLifecycleRepository(db).get_request(
            record.request_id
        )
        if record.state in TERMINAL_STATES:
            return (self._terminal_event(record),)
        failed = self._event(
            record,
            GenerationEventType.FAILED,
            record.last_emitted_sequence + 1,
            payload={"failure_class": failure_class, "retryable": retryable},
        )
        lifecycle.accept_event(self._fence(record), failed, now=datetime.now(UTC))
        record = SqlAlchemyResponseLifecycleRepository(db).get_request(
            record.request_id
        )
        lifecycle.mark_terminal(
            self._fence(record),
            target=ResponseRequestState.FAILED,
            reason=reason,
            retryable=retryable,
            failure_class=failure_class,
            now=datetime.now(UTC),
        )
        finish_session(db)
        return accepted, failed

    def _terminal_event(self, record) -> GenerationEvent:
        if record.state is ResponseRequestState.COMMITTED:
            event_type = GenerationEventType.COMPLETED
            payload = {}
        else:
            event_type = GenerationEventType.FAILED
            payload = {
                "failure_class": record.node_state.get("failure_class")
                or (
                    "generation_failed"
                    if record.terminal_reason is None
                    else record.terminal_reason.value
                ),
                "retryable": record.retryable,
            }
        return self._event(
            record, event_type, max(record.last_emitted_sequence, 0), payload=payload
        )

    def _fence(self, record) -> GenerationFence:
        return GenerationFence(
            request_id=record.request_id,
            thread_id=record.thread_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            lease_generation=record.lease_generation,
            expected_prior_state=record.state,
        )

    def _event(
        self,
        record,
        event_type: GenerationEventType,
        sequence: int,
        *,
        payload: dict | None = None,
    ) -> GenerationEvent:
        return GenerationEvent(
            request_id=record.request_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            sequence=sequence,
            event_type=event_type,
            payload=payload or {},
            protocol_version=CHAT_GENERATION_STREAM_VERSION,
        )

    @observe_generation
    async def stream_world_response(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        request_id: str,
        *,
        memory_recall_service: CanonicalRecallService | None,
        runtime_settings: Settings = settings,
    ) -> AsyncIterator[GenerationEvent]:
        thread = await session_call(db, lambda: self._mutation_thread(db, user, world_id, thread_id))
        repository = SqlAlchemyResponseLifecycleRepository(db)
        record = await session_call(db, lambda: repository.get_request(request_id))
        if record.thread_id != thread.id:
            raise MessageNotFoundError("응답 요청을 찾을 수 없습니다.")
        record = await session_call(db, lambda: self._recover_if_expired(db, record))
        if record.state in TERMINAL_STATES:
            yield self._terminal_event(record)
            return
        if record.state is not ResponseRequestState.ACCEPTED:
            raise MessageInFlightError("이 응답은 이미 처리 중입니다.")
        message, responding_character = await session_call(db, lambda: (
            db.get(models.MessageMessage, record.user_message_id), get_responding_character(db, thread.character_id)))
        if message is None or message.role != "user" or responding_character is None:
            async for event in self._fail_before_workflow(
                db,
                record,
                failure_class="canonical_context_missing",
                retryable=False,
                reason=ResponseTerminalReason.CONTRACT_INVALID,
            ):
                yield event
            return
        try:
            await session_call(db, lambda: self._validate_request_names(db, user, thread, record))
            configuration = self._request_configuration(thread, record.node_state)
            protocol = read_selection_protocol(record.node_state)
            if protocol == TEMPORAL_SELECTION_PROTOCOL:
                try:
                    fixed_time = ChatTimeContext.read(record.node_state.get(TIME_CONTEXT_KEY))
                    original_time = message.created_at.replace(tzinfo=UTC) if message.created_at.tzinfo is None else message.created_at
                    if (fixed_time.instant != original_time or fixed_time.timezone !=
                        EnvironmentSnapshot.from_dict(record.node_state["_environment"]).timezone):
                        raise ValueError("chat_time_context_binding_invalid")
                except (ValueError, TypeError, KeyError):
                    raise RetrievalContractError("chat_time_context_invalid") from None
            if protocol is not None and runtime_settings.CHAT_RECALL_MODE != "social_hybrid":
                raise RetrievalContractError("selection_protocol_mode_mismatch")
            if protocol in {NAME_SELECTION_PROTOCOL, ADVISORY_SELECTION_PROTOCOL, TEMPORAL_SELECTION_PROTOCOL} and "chat_identity_context.v1" not in record.node_state:
                raise RetrievalContractError("selection_protocol_identity_required")
        except RetrievalContractError:
            async for event in self._fail_before_workflow(db, record,
                failure_class="selection_protocol_invalid", retryable=False,
                reason=ResponseTerminalReason.CONTRACT_INVALID):
                yield event
            return
        except (MessageValidationError, NameBindingError):
            async for event in self._fail_before_workflow(db, record,
                failure_class="world_configuration_snapshot_invalid", retryable=False,
                reason=ResponseTerminalReason.CONTRACT_INVALID):
                yield event
            return
        if memory_recall_service is None:
            async for event in self._fail_before_workflow(
                db,
                record,
                failure_class="local_runtime_unavailable",
                retryable=True,
                reason=ResponseTerminalReason.RETRIEVAL_FAILURE,
            ):
                yield event
            return
        try:
            base_material = await session_call(db, lambda: self.workflows.resolve_credential(db, record.node_state, owner_id=user.id,
                world_id=thread.world_id, actor_id=thread.responding_world_character_id))
        except MessageCredentialRequiredError:
            async for event in self._fail_before_workflow(
                db,
                record,
                failure_class="credential_required",
                retryable=False,
                reason=ResponseTerminalReason.POLICY_DENIED,
            ):
                yield event
            return
        except MessageCredentialInvalidError:
            async for event in self._fail_before_workflow(
                db,
                record,
                failure_class="credential_invalid",
                retryable=False,
                reason=ResponseTerminalReason.POLICY_DENIED,
            ):
                yield event
            return
        material = CredentialMaterial(
            credential_id=base_material.credential_id,
            provider=base_material.provider,
            model=record.selected_model,
            thinking_level=record.selected_thinking_level,
            fingerprint=base_material.fingerprint,
            purpose=base_material.purpose,
            _secret=base_material.reveal(),
        )
        from app.domains.chat.contracts.initial_input import INPUT_KEY, read as read_initial_input, assert_available
        frozen_input = None
        try:
            assert_available(record.node_state)
        except RetrievalContractError:
            async for event in self._fail_before_workflow(db, record,
                    failure_class='initial_input_unavailable', retryable=False,
                    reason=ResponseTerminalReason.CONTRACT_INVALID):
                yield event
            return
        if INPUT_KEY in record.node_state:
            try:
                frozen_input = read_initial_input(record.node_state[INPUT_KEY],
                    request_scope_hash=record.request_scope_hash, response_slot_id=record.response_slot_id,
                    scope=(user.id, world_id, thread.id, thread.requester_world_character_id, thread.responding_world_character_id))
            except RetrievalContractError:
                async for event in self._fail_before_workflow(db, record,
                        failure_class='initial_input_invalid', retryable=False,
                        reason=ResponseTerminalReason.CONTRACT_INVALID):
                    yield event
                return
        image_observation = None
        if frozen_input is None and self.images is not None and not record.node_state.get("_image_excluded"):
            try:
                remaining = max(0.1, (record.deadline_at - datetime.now(UTC)).total_seconds())
                async with asyncio.timeout(remaining):
                    image_observation = await self.images.observation(db, user.id, thread.id, message.id)
                await session_call(db, lambda: self._mutation_thread(db, user, world_id, thread_id))
                record = await session_call(db, lambda: repository.get_request(request_id))
                if record.state in TERMINAL_STATES:
                    yield self._terminal_event(record)
                    return
                if record.state is not ResponseRequestState.ACCEPTED:
                    raise MessageValidationError("chat_request_changed_during_analysis")
            except Exception:
                async for event in self._fail_before_workflow(db, record,
                    failure_class="image_interpretation_unavailable", retryable=True,
                    reason=ResponseTerminalReason.RETRIEVAL_FAILURE):
                    yield event
                return
        message_context = (frozen_input.user_message if frozen_input else
            self.images.message_context(message.content, image_observation) if self.images else message.content)
        image_evidence = (frozen_input.image_evidence if frozen_input else
            self.images.evidence(user.id, thread.id, image_observation) if self.images else None)
        execution = await session_call(db, lambda: self.workflows.build(
            db,
            material,
            memory_recall_service=memory_recall_service,
            runtime_settings=runtime_settings,
            lifecycle=repository,
            world_id=world_id,
        ))
        character_labels = execution.character_labels
        from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext
        identity = ChatIdentityContext.read(record.node_state)
        if identity is not None:
            await session_call(db, lambda: identity.assert_scope(user.id, world_id, thread.id, thread.requester_world_character_id,
                thread.responding_world_character_id))
            character_labels.update(identity.names)
        workflow = execution.workflow
        router_context, response_context = ((frozen_input.router_context, frozen_input.response_context)
            if frozen_input else await session_call(db, lambda: _recent_context(
                db, thread.id, exclude_message_id=message.id, images=self.images, owner_id=user.id, identity=identity)))
        environment = EnvironmentSnapshot.from_dict(record.node_state.get("_environment"))
        today_sns_snapshot = frozen_input.today_sns_snapshot if frozen_input else None
        world = None if frozen_input else await session_call(db, lambda: get_character_entry_world(db, world_id))
        if frozen_input is None and world is not None and thread.responding_world_character_id is not None:
            try:
                today_sns_snapshot = await session_call(db, lambda: TodaySnsActivityAssembler(
                    self.workflows.today_reader(db)
                ).assemble(
                    owner_id=user.id,
                    world_id=world_id,
                    subject_world_character_id=thread.responding_world_character_id,
                    timezone=environment.timezone,
                    character_labels=character_labels,
                    label_reader=lambda ids: self.workflows.character_names(db, world_id, ids),
                    now=fixed_time.instant if protocol == TEMPORAL_SELECTION_PROTOCOL else datetime.now(UTC),
                ))
            except Exception as exc:
                logger.warning(
                    "p8_l_r_today_sns_snapshot_unavailable request_id=%s failure_type=%s",
                    record.request_id,
                    type(exc).__name__,
                )
        def build_command():
            return ResponseWorkflowCommand(
                request=record,
                preflight=RetrievalPreflightCommand(
                    request_id=record.request_id,
                    owner_id=user.id,
                    world_id=world_id,
                    thread_id=thread.id,
                    requester_world_character_id=thread.requester_world_character_id or "",
                    responding_world_character_id=thread.responding_world_character_id
                    or "",
                    user_message=message_context,
                    image_context=image_evidence.context if image_evidence else None,
                    environment=environment,
                ),
                profile=(frozen_input.profile if frozen_input else profiles._world_response_profile(configuration) if configuration is not None
                    else profiles._response_profile(responding_character)),
                router_context=router_context,
                response_context=response_context,
                character_labels=character_labels,
                today_sns_snapshot=today_sns_snapshot,
                graph_projection_enabled=runtime_settings.graph_projection_enabled,
                name_binding_validator=lambda: self._validate_request_input(db, user, thread, record, message.id, image_evidence),
                image_evidence=image_evidence,
                chat_identity=identity,
                identity_labels=lambda ids: self.workflows.character_names(db, world_id, ids),
            )
        command = await session_call(db, build_command)
        async for event in workflow.run(command):
            yield event

    def _validate_request_names(self, db, user, thread, record):
        from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext
        identity = ChatIdentityContext.read(record.node_state)
        if identity is not None:
            identity.assert_scope(user.id, thread.world_id, thread.id, thread.requester_world_character_id,
                thread.responding_world_character_id)
        self.workflows.assert_names_current(db, record.node_state, owner_id=user.id,
            world_id=thread.world_id, actor_id=thread.responding_world_character_id)

    def _validate_request_input(self, db, user, thread, record, message_id, evidence):
        self._mutation_thread(db, user, thread.world_id, thread.id)
        self.workflows.resolve_credential(db, record.node_state, owner_id=user.id,
            world_id=thread.world_id, actor_id=thread.responding_world_character_id)
        self._validate_request_names(db, user, thread, record)
        if self.images:
            self.images.assert_current(db, user.id, thread.id, message_id, evidence)


def _recent_context(
    db: Session, thread_id: str, *, exclude_message_id: int, images=None, owner_id=None, identity=None
) -> tuple[
    tuple[RetrievalRouterContextMessage, ...],
    tuple[CharacterResponseContextMessage, ...],
]:
    rows = request_repository.recent_context_messages(
        db,
        thread_id,
        exclude_message_id=exclude_message_id,
        limit=RESPONSE_CONTEXT_MESSAGE_LIMIT,
    )
    selected: list[models.MessageMessage] = []
    contents = {}
    chars = 0
    thread = db.get(models.MessageThread, thread_id)
    for row in reversed(rows):
        content = images.previous_context(db, owner_id, thread_id, row) if images else row.content
        author = thread.requester_world_character_id if row.role == "user" else thread.responding_world_character_id
        prefix = len(identity.names.get(author, "")) + 2 if identity is not None else 0
        if not content.strip() or chars + len(content) + prefix > RESPONSE_CONTEXT_CHAR_LIMIT:
            continue
        selected.append(row)
        contents[row.id] = content
        chars += len(content) + prefix
    selected.reverse()
    router = tuple(
        (
            RetrievalRouterContextMessage(role=row.role, content=contents[row.id],
                author_id=thread.requester_world_character_id if row.role == "user" else thread.responding_world_character_id)
            for row in selected
        )
    )
    response = tuple(
        (
            CharacterResponseContextMessage(role=row.role, content=contents[row.id], source_id=str(row.id),
                author_id=thread.requester_world_character_id if row.role == "user" else thread.responding_world_character_id)
            for row in selected
        )
    )
    return (router, response)
