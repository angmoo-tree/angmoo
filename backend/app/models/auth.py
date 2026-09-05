"""Compatibility facade for canonical identity domain models."""

from app.domains.identity.models import AuthExternalVerificationReservation
from app.domains.identity.models import AuthGoogleSignupGrant
from app.domains.identity.models import AuthLoginThrottleBucket
from app.domains.identity.models import AuthSession
from app.domains.identity.models import CommunityMutationQuotaBucket
from app.domains.identity.models import DISPLAY_NAME_CHANGE_COOLDOWN
from app.domains.identity.models import User

__all__ = [
    "AuthExternalVerificationReservation",
    "AuthGoogleSignupGrant",
    "AuthLoginThrottleBucket",
    "AuthSession",
    "CommunityMutationQuotaBucket",
    "DISPLAY_NAME_CHANGE_COOLDOWN",
    "User",
]
