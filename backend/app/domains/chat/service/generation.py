"""Durable generation admission, replay, status and terminal failure rules."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.chat import models, schemas
from app.domains.chat.contracts import (
    CHAT_GENERATION_STREAM_VERSION,
    TERMINAL_STATES,
    CreateResponseRequest,
    GenerationEvent,
    GenerationEventType,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
    build_request_scope_hash,
)
from app.domains.chat.contracts.context import ChatUser
from app.domains.chat.exceptions import (
    MessageInFlightError,
    MessageNotFoundError,
    MessageValidationError,
)
from app.domains.chat.repository import response_requests as request_repository
from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.domains.chat.service.threads import ThreadService

RESPONSE_REQUEST_DEADLINE_SECONDS = 180


class GenerationService:
    def __init__(self, thread_service: ThreadService) -> None:
        self.thread_service = thread_service

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
        if not content:
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
            if message is None or message.content != content:
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
                deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
            )
        )
        db.commit()
        db.refresh(message)
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
            if existing.retry_of_request_id != data.failed_request_id:
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
                deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
            )
        )
        db.commit()
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
