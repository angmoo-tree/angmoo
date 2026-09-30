"""Durable generation admission, replay, status and terminal failure rules."""

from __future__ import annotations
import asyncio
import json

from app.domains.chat.service.diagnostic_capture import capture

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
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
    ) -> None:
        self.thread_service = thread_service
        self.settings_service = settings_service
        self.workflows = workflows
        self.images = images

    def accept_world_message(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        data: schemas.WorldChatMessageCreate,
    ) -> schemas.WorldChatMessageAcceptRead:
        thread = self._mutation_thread(db, user, world_id, thread_id)
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
        selected_model = self.thread_service.resolve_world_thread_response_model(
            db, user, thread
        )
        now = datetime.now(UTC)
        message = models.MessageMessage(
            thread_id=thread.id, role="user", content=content, model=None, status="ok"
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
                request_metadata=self._request_names(db, user, thread),
            )
        )
        db.commit()
        db.refresh(message)
        capture.admit((user.id, world_id, thread_id), record.request_id)
        return schemas.WorldChatMessageAcceptRead(
            outcome="accepted",
            user_message=schemas.MessageMessageRead.model_validate(message),
            response_request=self._record_read(db, record),
        )

    def retry_world_response(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        data: schemas.WorldChatRetryCreate,
    ) -> schemas.WorldChatMessageAcceptRead:
        thread = self._mutation_thread(db, user, world_id, thread_id)
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
        exclude_image = data.exclude_attachment or bool(prior_metadata.get("_image_excluded"))
        if data.exclude_attachment and not prior_metadata.get("_image_excluded"):
            if (prior_metadata.get("failure_class") != "image_interpretation_unavailable"
                or not message.content.strip() or self.images is None
                or self.images.existing_asset(db, message.id) is None):
                raise MessageValidationError("image_text_only_recovery_unavailable")
        if self.images and not exclude_image:
            self.images.reserve_retry(db, user.id, thread.id, message.id)
        selected_model = self.thread_service.resolve_world_thread_response_model(
            db, user, thread
        )
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
                selected_thinking_level=thread.selected_thinking_level,
                deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
                request_metadata={**self._request_names(db, user, thread), "_image_excluded": exclude_image},
            )
        )
        db.commit()
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
        self._mutation_thread(db, user, world_id, thread_id)
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
        self._mutation_thread(db, user, world_id, thread_id)
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

    def _mutation_thread(
        self, db: Session, user: ChatUser, world_id: str, thread_id: str
    ) -> models.MessageThread:
        self.thread_service._require_world_chat_owner_scope(db, user.id, world_id)
        # Serialize admission with model PATCH before taking its model snapshot.
        thread = self.thread_service._get_owned_world_thread(
            db, user, world_id, thread_id, lock_thread=True
        )
        self.thread_service._world_thread_read(
            db, thread, include_messages=False, lock_scope=True
        )
        return thread

    def _request_names(self, db, user, thread):
        return self.workflows.capture_names(db, owner_id=user.id, world_id=thread.world_id,
            actor_id=thread.responding_world_character_id, requester_id=thread.requester_world_character_id)

    def _recover_if_expired(self, db: Session, record):
        now = datetime.now(UTC)
        if record.state in TERMINAL_STATES or record.deadline_at > now:
            return record
        repository = SqlAlchemyResponseLifecycleRepository(db)
        repository.recover_expired_requests(now=now, limit=100)
        db.commit()
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
            response_metadata={
                key: value
                for key, value in record.response_metadata.items()
                if not key.startswith("_")
            },
        )

    async def _fail_before_workflow(
        self,
        db: Session,
        record,
        *,
        failure_class: str,
        retryable: bool,
        reason: ResponseTerminalReason,
    ) -> AsyncIterator[GenerationEvent]:
        lifecycle = SqlAlchemyResponseLifecycleRepository(db)
        record = lifecycle.get_request(record.request_id)
        if record.state in TERMINAL_STATES:
            yield self._terminal_event(record)
            return
        now = datetime.now(UTC)
        record = lifecycle.acquire_lease(
            request_id=record.request_id,
            lease_token=f"lease-{uuid4().hex}",
            now=now,
            lease_expires_at=min(record.deadline_at, now + timedelta(seconds=30)),
        )
        db.commit()
        fence = self._fence(record)
        accepted = self._event(record, GenerationEventType.ACCEPTED, 0)
        lifecycle.accept_event(fence, accepted, now=datetime.now(UTC))
        db.commit()
        yield accepted
        record = SqlAlchemyResponseLifecycleRepository(db).get_request(
            record.request_id
        )
        if record.state in TERMINAL_STATES:
            yield self._terminal_event(record)
            return
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
        db.commit()
        yield failed

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
        thread = self._mutation_thread(db, user, world_id, thread_id)
        repository = SqlAlchemyResponseLifecycleRepository(db)
        record = repository.get_request(request_id)
        if record.thread_id != thread.id:
            raise MessageNotFoundError("응답 요청을 찾을 수 없습니다.")
        record = self._recover_if_expired(db, record)
        if record.state in TERMINAL_STATES:
            yield self._terminal_event(record)
            return
        if record.state is not ResponseRequestState.ACCEPTED:
            raise MessageInFlightError("이 응답은 이미 처리 중입니다.")
        message = db.get(models.MessageMessage, record.user_message_id)
        responding_character = get_responding_character(db, thread.character_id)
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
            _credential, base_material = (
                self.settings_service.resolve_message_credential_material(db, user)
            )
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
        image_observation = None
        if self.images is not None and not record.node_state.get("_image_excluded"):
            try:
                remaining = max(0.1, (record.deadline_at - datetime.now(UTC)).total_seconds())
                async with asyncio.timeout(remaining):
                    image_observation = await self.images.observation(db, user.id, thread.id, message.id)
                self._mutation_thread(db, user, world_id, thread_id)
                record = repository.get_request(request_id)
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
        message_context = self.images.message_context(message.content, image_observation) if self.images else message.content
        image_evidence = self.images.evidence(user.id, thread.id, image_observation) if self.images else None
        execution = self.workflows.build(
            db,
            material,
            memory_recall_service=memory_recall_service,
            runtime_settings=runtime_settings,
            lifecycle=repository,
            world_id=world_id,
        )
        character_labels = execution.character_labels
        workflow = execution.workflow
        router_context, response_context = _recent_context(
            db, thread.id, exclude_message_id=message.id, images=self.images, owner_id=user.id
        )
        today_sns_snapshot = None
        world = get_character_entry_world(db, world_id)
        if world is not None and thread.responding_world_character_id is not None:
            try:
                today_sns_snapshot = TodaySnsActivityAssembler(
                    self.workflows.today_reader(db)
                ).assemble(
                    owner_id=user.id,
                    world_id=world_id,
                    subject_world_character_id=thread.responding_world_character_id,
                    timezone=world.timezone,
                    character_labels=character_labels,
                    now=datetime.now(UTC),
                )
            except Exception as exc:
                logger.warning(
                    "p8_l_r_today_sns_snapshot_unavailable request_id=%s failure_type=%s",
                    record.request_id,
                    type(exc).__name__,
                )
        command = ResponseWorkflowCommand(
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
            ),
            profile=profiles._response_profile(responding_character),
            router_context=router_context,
            response_context=response_context,
            character_labels=character_labels,
            today_sns_snapshot=today_sns_snapshot,
            graph_projection_enabled=runtime_settings.graph_projection_enabled,
            name_binding_validator=lambda: self._validate_request_input(db, user, thread, record, message.id, image_evidence),
            image_evidence=image_evidence,
        )
        async for event in workflow.run(command):
            yield event

    def _validate_request_names(self, db, user, thread, record):
        self.workflows.assert_names_current(db, record.node_state, owner_id=user.id,
            world_id=thread.world_id, actor_id=thread.responding_world_character_id)

    def _validate_request_input(self, db, user, thread, record, message_id, evidence):
        self._mutation_thread(db, user, thread.world_id, thread.id)
        self._validate_request_names(db, user, thread, record)
        if self.images:
            self.images.assert_current(db, user.id, thread.id, message_id, evidence)


def _recent_context(
    db: Session, thread_id: str, *, exclude_message_id: int, images=None, owner_id=None
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
    for row in reversed(rows):
        content = images.previous_context(db, owner_id, thread_id, row) if images else row.content
        if not content.strip() or chars + len(content) > RESPONSE_CONTEXT_CHAR_LIMIT:
            continue
        selected.append(row)
        contents[row.id] = content
        chars += len(content)
    selected.reverse()
    router = tuple(
        (
            RetrievalRouterContextMessage(role=row.role, content=contents[row.id])
            for row in selected
        )
    )
    response = tuple(
        (
            CharacterResponseContextMessage(role=row.role, content=contents[row.id])
            for row in selected
        )
    )
    return (router, response)
