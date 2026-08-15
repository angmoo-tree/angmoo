"""Identity API contracts."""

from app.domains.identity.api.local_schemas import (
    LocalBootstrapChallengeRead,
    LocalBootstrapRead,
    LocalOwnerCandidateRead,
    LocalOwnerClaimCreate,
)
from app.domains.identity.api.schemas import (
    AccountDeletionCreate,
    AuthRead,
    FeedContentFilter,
    GoogleLinkCreate,
    GoogleLoginCreate,
    GoogleLoginRead,
    GoogleSignupCompleteCreate,
    LoginCreate,
    SignupCreate,
    UserDisplayNameUpdate,
    UserPreferencesUpdate,
    UserRead,
)

__all__ = [
    "AccountDeletionCreate",
    "AuthRead",
    "FeedContentFilter",
    "GoogleLinkCreate",
    "GoogleLoginCreate",
    "GoogleLoginRead",
    "GoogleSignupCompleteCreate",
    "LocalBootstrapChallengeRead",
    "LocalBootstrapRead",
    "LocalOwnerCandidateRead",
    "LocalOwnerClaimCreate",
    "LoginCreate",
    "SignupCreate",
    "UserDisplayNameUpdate",
    "UserPreferencesUpdate",
    "UserRead",
]
