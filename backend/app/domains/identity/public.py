"""Stable public imports for the identity domain.

Legacy modules re-export these objects while callers migrate incrementally.
"""

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
from app.domains.identity.application.resolve_credential import (
    CredentialResolutionError,
    CredentialResolver,
)
from app.domains.identity.domain.credential import CredentialMaterial, CredentialPurpose
from app.domains.identity.domain.local_owner import LOCAL_INSTALLATION_KEY
from app.domains.identity.infrastructure.sqlalchemy_auth_models import (
    AuthExternalVerificationReservation,
    AuthGoogleSignupGrant,
    AuthLoginThrottleBucket,
    AuthSession,
    CommunityMutationQuotaBucket,
    DISPLAY_NAME_CHANGE_COOLDOWN,
    InstallationIdentity,
    User,
)
from app.domains.identity.infrastructure.sqlalchemy_credential_models import (
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
