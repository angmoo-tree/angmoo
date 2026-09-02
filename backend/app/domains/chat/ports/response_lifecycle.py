"""Persistence port for response attempts, leases, events, and fenced commit."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

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


class ResponseLifecycleRepositoryPort(Protocol):
    def create_request(self, command: CreateResponseRequest) -> ResponseRequestRecord: ...

    def get_request(self, request_id: str) -> ResponseRequestRecord: ...

    def acquire_lease(
        self,
        *,
        request_id: str,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ResponseRequestRecord: ...

    def renew_lease(
        self,
        fence: GenerationFence,
        *,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> ResponseRequestRecord: ...

    def request_cancel(
        self,
        *,
        request_id: str,
        request_scope_hash: str,
        now: datetime,
    ) -> ResponseRequestRecord: ...

    def recover_expired_requests(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> tuple[ResponseRequestRecord, ...]: ...

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
    ) -> ResponseRequestRecord: ...

    def accept_event(
        self,
        fence: GenerationFence,
        event: GenerationEvent,
        *,
        now: datetime,
    ) -> SequenceOutcome: ...

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
    ) -> ResponseRequestRecord: ...

    def finalize_response(
        self,
        fence: GenerationFence,
        payload: ResponseCommitPayload,
        *,
        now: datetime,
    ) -> ResponseRequestRecord: ...


__all__ = ["ResponseLifecycleRepositoryPort"]
