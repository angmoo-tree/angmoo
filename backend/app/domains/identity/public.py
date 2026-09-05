"""Stable public imports for the identity domain.

Legacy modules re-export these objects while callers migrate incrementally.
"""

from app.domains.identity.schemas import (
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
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.identity.contracts import (
    CredentialMaterial,
    CredentialPurpose,
)
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import (
    AuthExternalVerificationReservation,
    AuthGoogleSignupGrant,
    AuthLoginThrottleBucket,
    AuthSession,
    CommunityMutationQuotaBucket,
    DISPLAY_NAME_CHANGE_COOLDOWN,
    InstallationIdentity,
    User,
    LlmCredential,
)

__all__ = [
    "AccountDeletionCreate",
    "AuthExternalVerificationReservation",
    "AuthGoogleSignupGrant",
    "AuthLoginThrottleBucket",
    "AuthRead",
    "AuthSession",
    "CommunityMutationQuotaBucket",
    "CredentialMaterial",
    "CredentialPurpose",
    "CredentialResolutionError",
    "CredentialResolver",
    "DISPLAY_NAME_CHANGE_COOLDOWN",
    "FeedContentFilter",
    "GoogleLinkCreate",
    "GoogleLoginCreate",
    "GoogleLoginRead",
    "GoogleSignupCompleteCreate",
    "InstallationIdentity",
    "LOCAL_INSTALLATION_KEY",
    "LoginCreate",
    "LlmCredential",
    "SignupCreate",
    "User",
    "UserDisplayNameUpdate",
    "UserPreferencesUpdate",
    "UserRead",
]
