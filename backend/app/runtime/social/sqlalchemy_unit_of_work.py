"""Immediate SQLite transaction execution and concrete owner collaboration."""
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from app.core.sqlite_concurrency import SqliteRetryPolicy, run_sqlite_session_immediate
from app.exceptions import SqliteBusyRetryExhausted
from app.domains.social.contracts.observations import SocialObservationCommand, SocialObservationResult
from app.domains.social.contracts.writes import OwnerPostCommand, OwnerReplyCommand, SocialWriteResult, SocialWriteRetryableError, ValidatedAutonomousWriteCommand
from app.domains.social.service.source_writes import SocialSourceWriteService
from app.domains.relationships.service import observations as observation_service
from app.runtime.relationships.observation_references import SqlAlchemyObservationReferences
from app.runtime.social.source_references import RuntimeSourceWriteReferences
from app.runtime.social.timeline import timeline_service

FailureInjector = Callable[[str], None]


class SqlAlchemySocialWriteUnitOfWork:
    """Run the source owner's operation inside the existing immediate transaction."""

    def __init__(self, session: Session, *, retry_policy: SqliteRetryPolicy | None = None, failure_injector: FailureInjector | None = None) -> None:
        self._session = session
        self._retry_policy = retry_policy
        self._service = SocialSourceWriteService(session, timeline=timeline_service, references=RuntimeSourceWriteReferences(session), failure_injector=failure_injector)


    def create_owner_post(self, command: OwnerPostCommand) -> SocialWriteResult:
        return self._run(lambda: self._service.create_owner_post(command))

    def create_owner_reply(self, command: OwnerReplyCommand) -> SocialWriteResult:
        return self._run(lambda: self._service.create_owner_reply(command))

    def apply_validated_autonomous_result(
        self, command: ValidatedAutonomousWriteCommand
    ) -> SocialWriteResult:
        """Persist validated output; no provider/LLM call is permitted here."""

        return self._run(lambda: self._service.apply_validated_autonomous_result(command))

    def _run(self, operation: Callable[[], SocialWriteResult]) -> SocialWriteResult:
        try:
            return run_sqlite_session_immediate(
                self._session,
                operation,
                retry_policy=self._retry_policy,
            )
        except SqliteBusyRetryExhausted as exc:
            raise SocialWriteRetryableError() from exc


class SqlAlchemySocialObservationUnitOfWork:
    """Connect the observation owner to the caller's existing transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._references = SqlAlchemyObservationReferences(session)

    def observe(self, command: SocialObservationCommand) -> SocialObservationResult:
        return observation_service.observe(self._session, command, references=self._references)


__all__ = [
    "SqlAlchemySocialObservationUnitOfWork",
    "SqlAlchemySocialWriteUnitOfWork",
]
