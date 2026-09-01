"""SQLAlchemy adapter for fenced response-attempt lifecycle persistence."""

from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.chat.domain.generation_lifecycle import (
    GenerationContractError,
    GenerationEvent,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
    SequenceOutcome,
    TERMINAL_STATES,
    validate_event_sequence,
    validate_transition,
)
from app.domains.chat.domain.response_request import (
    CreateResponseRequest,
    ResponseCommitPayload,
    ResponseRequestRecord,
)
from app.domains.chat.domain.retrieval_intent import RetrievalRoute
from app.domains.chat.domain.workflow_recipe import WorkflowRecipe
from app.domains.chat.infrastructure.sqlalchemy_models import (
    ChatResponseRequest,
    MessageMessage,
)


def _json_payload(value: dict | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SqlAlchemyResponseLifecycleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_request(self, command: CreateResponseRequest) -> ResponseRequestRecord:
        if (
            not command.request_id
            or not command.thread_id
            or not command.response_slot_id
            or not command.idempotency_key
            or not command.generation_id
            or not command.selected_model
            or command.user_message_id < 1
            or len(command.request_scope_hash) != 64
            or command.attempt_number < 1
            or command.deadline_at <= datetime.min.replace(tzinfo=command.deadline_at.tzinfo)
        ):
            raise GenerationContractError("response_request_create_invalid")
        existing = self._find_by_idempotency(command.thread_id, command.idempotency_key)
        if existing is not None:
            self._assert_create_replay(existing, command)
            return self._to_record(existing)
        self._validate_retry_lineage(command)
        row = ChatResponseRequest(
            request_id=command.request_id,
            thread_id=command.thread_id,
            user_message_id=command.user_message_id,
            response_slot_id=command.response_slot_id,
            request_scope_hash=command.request_scope_hash,
            idempotency_key=command.idempotency_key,
            generation_id=command.generation_id,
            attempt_number=command.attempt_number,
            retry_of_request_id=command.retry_of_request_id,
            selected_model=command.selected_model,
            deadline_at=command.deadline_at,
            state=ResponseRequestState.ACCEPTED.value,
            last_emitted_sequence=-1,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            existing = self._find_by_idempotency(
                command.thread_id,
                command.idempotency_key,
            )
            if existing is None:
                raise GenerationContractError("response_request_create_conflict") from None
            self._assert_create_replay(existing, command)
            return self._to_record(existing)
        self._session.refresh(row)
        return self._to_record(row)

    def get_request(self, request_id: str) -> ResponseRequestRecord:
        return self._to_record(self._require(request_id))

    def acquire_lease(
        self,
        *,
        request_id: str,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ResponseRequestRecord:
        if not lease_token or lease_expires_at <= now:
            raise GenerationContractError("response_lease_window_invalid")
        statement = (
            update(ChatResponseRequest)
            .execution_options(synchronize_session=False)
            .where(
                ChatResponseRequest.request_id == request_id,
                ChatResponseRequest.state == ResponseRequestState.ACCEPTED.value,
                or_(
                    ChatResponseRequest.lease_token.is_(None),
                    ChatResponseRequest.lease_expires_at <= now,
                ),
                ChatResponseRequest.deadline_at > now,
            )
            .values(
                state=ResponseRequestState.LEASE_ACQUIRED.value,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                lease_generation=ChatResponseRequest.lease_generation + 1,
                updated_at=now,
            )
        )
        if self._session.execute(statement).rowcount != 1:
            raise GenerationContractError("response_lease_acquire_conflict")
        self._session.flush()
        return self._to_record(self._require(request_id, populate_existing=True))

    def renew_lease(
        self,
        fence: GenerationFence,
        *,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ResponseRequestRecord:
        if not lease_token or lease_expires_at <= now:
            raise GenerationContractError("response_lease_window_invalid")
        statement = (
            update(ChatResponseRequest)
            .execution_options(synchronize_session=False)
            .where(
                *self._fenced_conditions(fence),
                ChatResponseRequest.lease_token == lease_token,
                ChatResponseRequest.lease_expires_at > now,
                ChatResponseRequest.deadline_at > now,
            )
            .values(
                lease_expires_at=lease_expires_at,
                lease_generation=ChatResponseRequest.lease_generation + 1,
                updated_at=now,
            )
        )
        if self._session.execute(statement).rowcount != 1:
            raise GenerationContractError("response_lease_renew_conflict")
        self._session.flush()
        return self._to_record(self._require(fence.request_id, populate_existing=True))

    def request_cancel(
        self,
        *,
        request_id: str,
        request_scope_hash: str,
        now: datetime,
    ) -> ResponseRequestRecord:
        if len(request_scope_hash) != 64:
            raise GenerationContractError("response_cancel_scope_invalid")
        result = self._session.execute(
            update(ChatResponseRequest)
            .execution_options(synchronize_session=False)
            .where(
                ChatResponseRequest.request_id == request_id,
                ChatResponseRequest.request_scope_hash == request_scope_hash,
                ChatResponseRequest.state.not_in(
                    tuple(state.value for state in TERMINAL_STATES)
                ),
                ChatResponseRequest.cancel_requested_at.is_(None),
            )
            .values(
                state=ResponseRequestState.CANCELLED.value,
                terminal_reason=ResponseTerminalReason.USER_CANCELLED.value,
                retryable=False,
                lease_token=None,
                lease_expires_at=None,
                cancel_requested_at=now,
                terminal_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            row = self._require(request_id, populate_existing=True)
            if (
                row.request_scope_hash == request_scope_hash
                and row.state == ResponseRequestState.CANCELLED.value
                and row.terminal_reason == ResponseTerminalReason.USER_CANCELLED.value
            ):
                return self._to_record(row)
            raise GenerationContractError("response_cancel_conflict")
        self._session.flush()
        return self._to_record(self._require(request_id, populate_existing=True))

    def recover_expired_requests(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> tuple[ResponseRequestRecord, ...]:
        if not 1 <= limit <= 1_000:
            raise GenerationContractError("response_recovery_limit_invalid")
        candidates = tuple(
            self._session.scalars(
                select(ChatResponseRequest)
                .where(
                    ChatResponseRequest.state.not_in(
                        tuple(state.value for state in TERMINAL_STATES)
                    ),
                    or_(
                        ChatResponseRequest.deadline_at <= now,
                        (
                            ChatResponseRequest.lease_token.is_not(None)
                            & (ChatResponseRequest.lease_expires_at <= now)
                        ),
                    ),
                )
                .order_by(ChatResponseRequest.updated_at, ChatResponseRequest.request_id)
                .limit(limit)
            )
        )
        recovered: list[ResponseRequestRecord] = []
        for row in candidates:
            cancelled = row.cancel_requested_at is not None
            timed_out = _as_utc(row.deadline_at) <= _as_utc(now)
            if cancelled:
                target = ResponseRequestState.CANCELLED
                reason = ResponseTerminalReason.USER_CANCELLED
                retryable = False
            elif timed_out:
                target = ResponseRequestState.TIMED_OUT
                reason = ResponseTerminalReason.DEADLINE_EXCEEDED
                retryable = True
            else:
                target = ResponseRequestState.ORPHANED
                reason = ResponseTerminalReason.ORPHAN_RECOVERED
                retryable = True
            result = self._session.execute(
                update(ChatResponseRequest)
                .execution_options(synchronize_session=False)
                .where(
                    ChatResponseRequest.request_id == row.request_id,
                    ChatResponseRequest.state == row.state,
                    ChatResponseRequest.lease_generation == row.lease_generation,
                    ChatResponseRequest.state.not_in(
                        tuple(state.value for state in TERMINAL_STATES)
                    ),
                )
                .values(
                    state=target.value,
                    terminal_reason=reason.value,
                    retryable=retryable,
                    lease_token=None,
                    lease_expires_at=None,
                    terminal_at=now,
                    updated_at=now,
                )
            )
            if result.rowcount == 1:
                self._session.flush()
                recovered.append(
                    self._to_record(
                        self._require(row.request_id, populate_existing=True)
                    )
                )
        return tuple(recovered)

    def transition(
        self,
        fence: GenerationFence,
        *,
        target: ResponseRequestState,
        now: datetime,
        route: RetrievalRoute | None = None,
        workflow_recipe: WorkflowRecipe | None = None,
        node_state: dict | None = None,
        call_tracker: dict | None = None,
    ) -> ResponseRequestRecord:
        validate_transition(fence.expected_prior_state, target)
        values: dict = {"state": target.value, "updated_at": now}
        if route is not None:
            values["route"] = route.value
        if workflow_recipe is not None:
            values["workflow_recipe"] = workflow_recipe.value
        if node_state is not None:
            values["node_state_json"] = _json_payload(node_state)
        if call_tracker is not None:
            values["call_tracker_json"] = _json_payload(call_tracker)
        if self._session.execute(
            update(ChatResponseRequest)
            .execution_options(synchronize_session=False)
            .where(*self._active_fenced_conditions(fence, now=now))
            .values(**values)
        ).rowcount != 1:
            raise GenerationContractError("response_transition_fence_conflict")
        self._session.flush()
        return self._to_record(self._require(fence.request_id, populate_existing=True))

    def accept_event(
        self,
        fence: GenerationFence,
        event: GenerationEvent,
        *,
        now: datetime,
    ) -> SequenceOutcome:
        row = self._require(fence.request_id, populate_existing=True)
        self._assert_fence(row, fence)
        if _as_utc(row.deadline_at) <= _as_utc(now):
            raise GenerationContractError("response_event_after_deadline")
        outcome = validate_event_sequence(
            fence,
            event,
            last_emitted_sequence=row.last_emitted_sequence,
        )
        if outcome is SequenceOutcome.DUPLICATE:
            return outcome
        result = self._session.execute(
            update(ChatResponseRequest)
            .execution_options(synchronize_session=False)
            .where(
                *self._active_fenced_conditions(fence, now=now),
                ChatResponseRequest.last_emitted_sequence
                == row.last_emitted_sequence,
            )
            .values(last_emitted_sequence=event.sequence, updated_at=now)
        )
        if result.rowcount != 1:
            raise GenerationContractError("response_event_fence_conflict")
        self._session.flush()
        return SequenceOutcome.ACCEPTED

    def mark_terminal(
        self,
        fence: GenerationFence,
        *,
        target: ResponseRequestState,
        reason: ResponseTerminalReason,
        retryable: bool,
        now: datetime,
    ) -> ResponseRequestRecord:
        if target not in TERMINAL_STATES or target is ResponseRequestState.COMMITTED:
            raise GenerationContractError("response_terminal_target_invalid")
        validate_transition(fence.expected_prior_state, target)
        result = self._session.execute(
            update(ChatResponseRequest)
            .execution_options(synchronize_session=False)
            .where(*self._fenced_conditions(fence))
            .values(
                state=target.value,
                terminal_reason=reason.value,
                retryable=retryable,
                lease_token=None,
                lease_expires_at=None,
                terminal_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise GenerationContractError("response_terminal_fence_conflict")
        self._session.flush()
        return self._to_record(self._require(fence.request_id, populate_existing=True))

    def finalize_response(
        self,
        fence: GenerationFence,
        payload: ResponseCommitPayload,
        *,
        now: datetime,
    ) -> ResponseRequestRecord:
        existing = self._require(fence.request_id, populate_existing=True)
        if existing.state == ResponseRequestState.COMMITTED.value:
            self._assert_identity_fence(existing, fence)
            return self._to_record(existing)
        if fence.expected_prior_state is not ResponseRequestState.COMMITTING:
            raise GenerationContractError("response_finalize_prior_state_invalid")
        if _as_utc(existing.deadline_at) <= _as_utc(now):
            raise GenerationContractError("response_finalize_after_deadline")
        tracker = self._decode_json(existing.call_tracker_json)
        logical = tracker.get("logical_counts", {})
        if logical.get("character_response_generator") != 1:
            raise GenerationContractError("response_finalize_crg_count_invalid")
        metadata = payload.metadata
        if (
            metadata.request_id != existing.request_id
            or metadata.request_scope_hash != existing.request_scope_hash
            or metadata.generation_id != existing.generation_id
            or metadata.attempt_number != existing.attempt_number
            or metadata.retry_of_request_id != existing.retry_of_request_id
            or metadata.last_accepted_sequence != existing.last_emitted_sequence
            or existing.route != metadata.route.value
            or (
                None
                if metadata.workflow_recipe is None
                else metadata.workflow_recipe.value
            )
            != existing.workflow_recipe
        ):
            raise GenerationContractError("response_finalize_metadata_mismatch")
        metadata_json = _json_payload(metadata.payload())
        try:
            with self._session.begin_nested():
                assistant = MessageMessage(
                    thread_id=existing.thread_id,
                    role="assistant",
                    content=payload.content,
                    model=payload.model,
                    status="ok",
                )
                self._session.add(assistant)
                self._session.flush()
                result = self._session.execute(
                    update(ChatResponseRequest)
                    .execution_options(synchronize_session=False)
                    .where(*self._active_fenced_conditions(fence, now=now))
                    .values(
                        state=ResponseRequestState.COMMITTED.value,
                        terminal_reason=ResponseTerminalReason.COMMITTED.value,
                        retryable=False,
                        committed_assistant_message_id=assistant.id,
                        response_metadata_json=metadata_json,
                        lease_token=None,
                        lease_expires_at=None,
                        terminal_at=now,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    raise GenerationContractError("response_finalize_fence_conflict")
                self._session.flush()
        except IntegrityError as exc:
            raise GenerationContractError("response_finalize_integrity_conflict") from exc
        return self._to_record(self._require(fence.request_id, populate_existing=True))

    def _fenced_conditions(self, fence: GenerationFence) -> tuple:
        return (
            ChatResponseRequest.request_id == fence.request_id,
            ChatResponseRequest.thread_id == fence.thread_id,
            ChatResponseRequest.request_scope_hash == fence.request_scope_hash,
            ChatResponseRequest.generation_id == fence.generation_id,
            ChatResponseRequest.attempt_number == fence.attempt_number,
            ChatResponseRequest.lease_generation == fence.lease_generation,
            ChatResponseRequest.state == fence.expected_prior_state.value,
        )

    def _active_fenced_conditions(self, fence: GenerationFence, *, now: datetime) -> tuple:
        return self._fenced_conditions(fence) + (
            ChatResponseRequest.lease_token.is_not(None),
            ChatResponseRequest.lease_expires_at > now,
            ChatResponseRequest.deadline_at > now,
            ChatResponseRequest.cancel_requested_at.is_(None),
        )

    def _assert_fence(self, row: ChatResponseRequest, fence: GenerationFence) -> None:
        self._assert_identity_fence(row, fence)
        if (
            row.lease_generation != fence.lease_generation
            or row.state != fence.expected_prior_state.value
        ):
            raise GenerationContractError("response_generation_fence_mismatch")

    @staticmethod
    def _assert_identity_fence(row: ChatResponseRequest, fence: GenerationFence) -> None:
        if (
            row.request_id != fence.request_id
            or row.thread_id != fence.thread_id
            or row.request_scope_hash != fence.request_scope_hash
            or row.generation_id != fence.generation_id
            or row.attempt_number != fence.attempt_number
        ):
            raise GenerationContractError("response_generation_identity_mismatch")

    def _require(self, request_id: str, *, populate_existing: bool = False) -> ChatResponseRequest:
        statement = select(ChatResponseRequest).where(
            ChatResponseRequest.request_id == request_id
        )
        if populate_existing:
            statement = statement.execution_options(populate_existing=True)
        row = self._session.scalar(statement)
        if row is None:
            raise GenerationContractError("response_request_not_found")
        return row

    def _find_by_idempotency(
        self,
        thread_id: str,
        idempotency_key: str,
    ) -> ChatResponseRequest | None:
        return self._session.scalar(
            select(ChatResponseRequest).where(
                ChatResponseRequest.thread_id == thread_id,
                ChatResponseRequest.idempotency_key == idempotency_key,
            )
        )

    def _validate_retry_lineage(self, command: CreateResponseRequest) -> None:
        if command.retry_of_request_id is None:
            if command.attempt_number != 1:
                raise GenerationContractError("response_retry_lineage_missing")
            return
        prior = self._session.get(ChatResponseRequest, command.retry_of_request_id)
        if prior is None:
            raise GenerationContractError("response_retry_parent_not_found")
        if (
            prior.state not in {state.value for state in TERMINAL_STATES}
            or not prior.retryable
            or prior.committed_assistant_message_id is not None
        ):
            raise GenerationContractError("response_retry_parent_not_retryable")
        if (
            command.request_id == prior.request_id
            or command.generation_id == prior.generation_id
            or command.thread_id != prior.thread_id
            or command.user_message_id != prior.user_message_id
            or command.response_slot_id != prior.response_slot_id
            or command.request_scope_hash != prior.request_scope_hash
            or command.attempt_number != prior.attempt_number + 1
        ):
            raise GenerationContractError("response_retry_lineage_mismatch")

    @staticmethod
    def _assert_create_replay(
        row: ChatResponseRequest,
        command: CreateResponseRequest,
    ) -> None:
        if (
            row.user_message_id != command.user_message_id
            or row.response_slot_id != command.response_slot_id
            or row.request_scope_hash != command.request_scope_hash
            or row.generation_id != command.generation_id
            or row.attempt_number != command.attempt_number
        ):
            raise GenerationContractError("response_request_idempotency_mismatch")

    @staticmethod
    def _decode_json(value: str) -> dict:
        try:
            payload = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise GenerationContractError("response_request_json_corrupt") from exc
        if not isinstance(payload, dict):
            raise GenerationContractError("response_request_json_corrupt")
        return payload

    def _to_record(self, row: ChatResponseRequest) -> ResponseRequestRecord:
        return ResponseRequestRecord(
            request_id=row.request_id,
            thread_id=row.thread_id,
            user_message_id=row.user_message_id,
            response_slot_id=row.response_slot_id,
            request_scope_hash=row.request_scope_hash,
            idempotency_key=row.idempotency_key,
            generation_id=row.generation_id,
            attempt_number=row.attempt_number,
            selected_model=row.selected_model,
            deadline_at=_as_utc(row.deadline_at),
            state=ResponseRequestState(row.state),
            lease_generation=row.lease_generation,
            lease_token=row.lease_token,
            lease_expires_at=(
                None if row.lease_expires_at is None else _as_utc(row.lease_expires_at)
            ),
            retry_of_request_id=row.retry_of_request_id,
            route=None if row.route is None else RetrievalRoute(row.route),
            workflow_recipe=(
                None
                if row.workflow_recipe is None
                else WorkflowRecipe(row.workflow_recipe)
            ),
            last_emitted_sequence=row.last_emitted_sequence,
            terminal_reason=(
                None
                if row.terminal_reason is None
                else ResponseTerminalReason(row.terminal_reason)
            ),
            retryable=row.retryable,
            committed_assistant_message_id=row.committed_assistant_message_id,
            node_state=self._decode_json(row.node_state_json),
            call_tracker=self._decode_json(row.call_tracker_json),
            response_metadata=self._decode_json(row.response_metadata_json),
            created_at=None if row.created_at is None else _as_utc(row.created_at),
            updated_at=None if row.updated_at is None else _as_utc(row.updated_at),
            terminal_at=None if row.terminal_at is None else _as_utc(row.terminal_at),
            cancel_requested_at=(
                None
                if row.cancel_requested_at is None
                else _as_utc(row.cancel_requested_at)
            ),
        )


__all__ = ["SqlAlchemyResponseLifecycleRepository"]
