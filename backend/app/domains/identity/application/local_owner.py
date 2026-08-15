from __future__ import annotations

from datetime import datetime, timezone

from app.domains.identity.domain.local_owner import (
    IssuedBootstrapChallenge,
    IssuedLocalSession,
    LocalBootstrapStatus,
)
from app.domains.identity.ports.identity_repository import IdentityRepository


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GetLocalBootstrapStatus:
    def __init__(self, repository: IdentityRepository) -> None:
        self._repository = repository

    def execute(self) -> LocalBootstrapStatus:
        return self._repository.get_bootstrap_status()


class CreateLocalBootstrapChallenge:
    def __init__(self, repository: IdentityRepository) -> None:
        self._repository = repository

    def execute(self) -> IssuedBootstrapChallenge:
        return self._repository.create_bootstrap_challenge(now=utcnow())


class ClaimLocalOwner:
    def __init__(self, repository: IdentityRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        challenge_token: str,
        owner_user_id: str | None,
        display_name: str | None,
        local_label: str | None,
        privacy_acknowledged: bool,
    ) -> IssuedLocalSession:
        return self._repository.claim_local_owner(
            challenge_token=challenge_token,
            owner_user_id=owner_user_id,
            display_name=display_name,
            local_label=local_label,
            privacy_acknowledged=privacy_acknowledged,
            now=utcnow(),
        )


class IssueLocalSession:
    def __init__(self, repository: IdentityRepository) -> None:
        self._repository = repository

    def execute(self, *, secret_ready: bool) -> IssuedLocalSession:
        return self._repository.issue_local_session(
            now=utcnow(),
            secret_ready=secret_ready,
        )
