from app.core.response_schemas import UtcInstantResponseModel
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.identity.contracts import (
    IssuedLocalSession,
    LocalBootstrapStatus,
    LocalOwnerCandidate,
    LocalUserSnapshot,
)

FeedContentFilter = Literal["all", "posts", "reposts"]


class SignupCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=80)
    privacy_policy_agreed: bool = False
    terms_agreed: bool = False
    turnstile_token: str | None = Field(default=None, max_length=2048)


class LoginCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class GoogleLoginCreate(BaseModel):
    credential: str = Field(min_length=1)


class GoogleSignupCompleteCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    privacy_policy_agreed: bool = False
    terms_agreed: bool = False
    turnstile_token: str | None = Field(default=None, max_length=2048)


class GoogleLinkCreate(BaseModel):
    credential: str = Field(min_length=1)


class UserDisplayNameUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    privacy_policy_agreed: bool | None = None
    terms_agreed: bool | None = None


class UserPreferencesUpdate(BaseModel):
    feed_content_filter: FeedContentFilter


class AccountDeletionCreate(BaseModel):
    confirmation: str = Field(min_length=1, max_length=20)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None = None
    display_name: str
    display_name_updated_at: datetime | None = None
    display_name_change_available_at: datetime | None = None
    profile_setup_completed: bool
    feed_content_filter: FeedContentFilter = "all"
    is_admin: bool = False


class AuthRead(BaseModel):
    user: UserRead
    profile_setup_required: bool = False


class GoogleLoginRead(BaseModel):
    user: UserRead | None = None
    profile_setup_required: bool = False
    signup_required: bool = False
    expires_at: datetime | None = None
    email: str | None = None


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


class CredentialRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    character_id: str | None = None
    provider: str
    purpose: str
    model: str
    label: str
    key_fingerprint: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    cooldown_until: datetime | None = None
