from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


LOCAL_INSTALLATION_KEY = "local-installation"
BootstrapState = Literal["unclaimed", "claimed", "recovery_required"]


class LocalIdentityError(Exception):
    code = "local_identity_error"


class LocalOwnerUnclaimedError(LocalIdentityError):
    code = "local_owner_unclaimed"


class BootstrapClosedError(LocalIdentityError):
    code = "bootstrap_closed"


class BootstrapChallengeInvalidError(LocalIdentityError):
    code = "bootstrap_challenge_invalid"


class BootstrapRaceLostError(LocalIdentityError):
    code = "bootstrap_race_lost"


class LocalOwnerCandidateInvalidError(LocalIdentityError):
    code = "local_owner_candidate_invalid"


class LocalOwnerProfileInvalidError(LocalIdentityError):
    code = "local_owner_profile_invalid"


class LocalOwnerPrivacyAcknowledgementRequiredError(LocalIdentityError):
    code = "local_owner_privacy_acknowledgement_required"


class LocalSessionRateLimitedError(LocalIdentityError):
    code = "local_session_rate_limited"


class LocalSessionUnavailableError(LocalIdentityError):
    code = "app_secret_missing"


@dataclass(frozen=True)
class LocalOwnerCandidate:
    user_id: str
    display_name: str
    character_count: int
    world_count: int
    credential_count: int

    @property
    def activity_count(self) -> int:
        return self.character_count + self.world_count + self.credential_count


@dataclass(frozen=True)
class LocalUserSnapshot:
    user_id: str
    email: str | None
    display_name: str
    profile_setup_completed: bool
    feed_content_filter: str
    is_admin: bool


@dataclass(frozen=True)
class LocalBootstrapStatus:
    state: BootstrapState
    installation_id: str | None
    local_label: str | None
    owner: LocalUserSnapshot | None
    candidates: tuple[LocalOwnerCandidate, ...]


@dataclass(frozen=True)
class IssuedBootstrapChallenge:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class IssuedLocalSession:
    token: str
    expires_at: datetime
    user: LocalUserSnapshot


def normalize_local_display_name(value: str | None) -> tuple[str, str]:
    display_name = " ".join((value or "").strip().split())
    if not display_name or len(display_name) > 80:
        raise LocalOwnerProfileInvalidError("invalid local owner display name")
    return display_name, display_name.casefold()


def normalize_local_label(value: str | None) -> str | None:
    label = " ".join((value or "").strip().split())
    if not label:
        return None
    if len(label) > 80:
        raise LocalOwnerProfileInvalidError("invalid local installation label")
    return label
