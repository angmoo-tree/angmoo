from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domains.identity.api.schemas import AuthRead, UserRead
from app.domains.identity.domain.local_owner import (
    IssuedLocalSession,
    LocalBootstrapStatus,
    LocalOwnerCandidate,
    LocalUserSnapshot,
)


class LocalOwnerCandidateRead(BaseModel):
    user_id: str
    display_name: str
    character_count: int
    world_count: int
    credential_count: int
    suggested: bool = False


class LocalBootstrapRead(BaseModel):
    state: Literal["unclaimed", "claimed", "recovery_required"]
    installation_id: str | None = None
    local_label: str | None = None
    owner: UserRead | None = None
    candidates: list[LocalOwnerCandidateRead] = Field(default_factory=list)


class LocalBootstrapChallengeRead(BaseModel):
    expires_at: datetime


class LocalOwnerClaimCreate(BaseModel):
    owner_user_id: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, max_length=80)
    local_label: str | None = Field(default=None, max_length=80)
    privacy_acknowledged: bool = False


def bootstrap_read(status: LocalBootstrapStatus) -> LocalBootstrapRead:
    single_candidate_id = (
        status.candidates[0].user_id
        if len(status.candidates) == 1
        else None
    )
    return LocalBootstrapRead(
        state=status.state,
        installation_id=status.installation_id,
        local_label=status.local_label,
        owner=_user_read(status.owner) if status.owner else None,
        candidates=[
            _candidate_read(
                candidate,
                suggested=candidate.user_id == single_candidate_id,
            )
            for candidate in status.candidates
        ],
    )


def auth_read(issued: IssuedLocalSession) -> AuthRead:
    return AuthRead(user=_user_read(issued.user), profile_setup_required=False)


def _candidate_read(
    candidate: LocalOwnerCandidate,
    *,
    suggested: bool,
) -> LocalOwnerCandidateRead:
    return LocalOwnerCandidateRead(
        user_id=candidate.user_id,
        display_name=candidate.display_name,
        character_count=candidate.character_count,
        world_count=candidate.world_count,
        credential_count=candidate.credential_count,
        suggested=suggested,
    )


def _user_read(user: LocalUserSnapshot) -> UserRead:
    return UserRead(
        id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        display_name_updated_at=None,
        display_name_change_available_at=None,
        profile_setup_completed=user.profile_setup_completed,
        feed_content_filter=user.feed_content_filter,
        is_admin=user.is_admin,
    )
