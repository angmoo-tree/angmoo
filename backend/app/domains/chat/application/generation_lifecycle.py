"""Application service for response-attempt lifecycle commands."""

from __future__ import annotations

from datetime import datetime

from app.domains.chat.domain.generation_lifecycle import (
    GenerationEvent,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
    SequenceOutcome,
)
from app.domains.chat.domain.response_request import (
    CreateResponseRequest,
    ResponseCommitPayload,
    ResponseRequestRecord,
)
from app.domains.chat.domain.retrieval_intent import RetrievalRoute
from app.domains.chat.domain.workflow_recipe import WorkflowRecipe
from app.domains.chat.ports.response_lifecycle import ResponseLifecycleRepositoryPort


class GenerationLifecycleService:
    def __init__(self, repository: ResponseLifecycleRepositoryPort) -> None:
        self._repository = repository

    def accept(self, command: CreateResponseRequest) -> ResponseRequestRecord:
        return self._repository.create_request(command)

    def acquire_lease(
        self,
        *,
        request_id: str,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ResponseRequestRecord:
        return self._repository.acquire_lease(
            request_id=request_id,
            lease_token=lease_token,
            now=now,
            lease_expires_at=lease_expires_at,
        )

    def renew_lease(
        self,
        fence: GenerationFence,
        *,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ResponseRequestRecord:
        return self._repository.renew_lease(
            fence,
            lease_token=lease_token,
            now=now,
            lease_expires_at=lease_expires_at,
        )

    def request_cancel(
        self,
        *,
        request_id: str,
        request_scope_hash: str,
        now: datetime,
    ) -> ResponseRequestRecord:
        return self._repository.request_cancel(
            request_id=request_id,
            request_scope_hash=request_scope_hash,
            now=now,
        )

    def recover_expired_requests(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> tuple[ResponseRequestRecord, ...]:
        return self._repository.recover_expired_requests(now=now, limit=limit)

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
        return self._repository.transition(
            fence,
            target=target,
            now=now,
            route=route,
            workflow_recipe=workflow_recipe,
            node_state=node_state,
            call_tracker=call_tracker,
        )

    def accept_event(
        self,
        fence: GenerationFence,
        event: GenerationEvent,
        *,
        now: datetime,
    ) -> SequenceOutcome:
        return self._repository.accept_event(fence, event, now=now)

    def mark_terminal(
        self,
        fence: GenerationFence,
        *,
        target: ResponseRequestState,
        reason: ResponseTerminalReason,
        retryable: bool,
        failure_class: str | None = None,
        failure_diagnostic: dict | None = None,
        call_tracker: dict | None = None,
        now: datetime,
    ) -> ResponseRequestRecord:
        return self._repository.mark_terminal(
            fence,
            target=target,
            reason=reason,
            retryable=retryable,
            failure_class=failure_class,
            failure_diagnostic=failure_diagnostic,
            call_tracker=call_tracker,
            now=now,
        )

    def finalize(
        self,
        fence: GenerationFence,
        payload: ResponseCommitPayload,
        *,
        now: datetime,
    ) -> ResponseRequestRecord:
        return self._repository.finalize_response(fence, payload, now=now)


__all__ = ["GenerationLifecycleService"]
