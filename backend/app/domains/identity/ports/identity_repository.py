from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domains.identity.domain.local_owner import (
    IssuedBootstrapChallenge,
    IssuedLocalSession,
    LocalBootstrapStatus,
)


class IdentityRepository(Protocol):
    def ensure_local_installation_identity(self, *, now: datetime) -> str: ...

    def get_bootstrap_status(self) -> LocalBootstrapStatus: ...

    def create_bootstrap_challenge(
        self,
        *,
        now: datetime,
    ) -> IssuedBootstrapChallenge: ...

    def claim_local_owner(
        self,
        *,
        challenge_token: str,
        owner_user_id: str | None,
        display_name: str | None,
        local_label: str | None,
        privacy_acknowledged: bool,
        now: datetime,
    ) -> IssuedLocalSession: ...

    def issue_local_session(
        self,
        *,
        now: datetime,
        secret_ready: bool,
    ) -> IssuedLocalSession: ...
