"""Compatibility facade for canonical identity API schemas."""

from app.domains.identity.schemas import AccountDeletionCreate
from app.domains.identity.schemas import AuthRead
from app.domains.identity.schemas import FeedContentFilter
from app.domains.identity.schemas import GoogleLinkCreate
from app.domains.identity.schemas import GoogleLoginCreate
from app.domains.identity.schemas import GoogleLoginRead
from app.domains.identity.schemas import GoogleSignupCompleteCreate
from app.domains.identity.schemas import LoginCreate
from app.domains.identity.schemas import SignupCreate
from app.domains.identity.schemas import UserDisplayNameUpdate
from app.domains.identity.schemas import UserPreferencesUpdate
from app.domains.identity.schemas import UserRead

__all__ = [
    "AccountDeletionCreate",
    "AuthRead",
    "FeedContentFilter",
    "GoogleLinkCreate",
    "GoogleLoginCreate",
    "GoogleLoginRead",
    "GoogleSignupCompleteCreate",
    "LoginCreate",
    "SignupCreate",
    "UserDisplayNameUpdate",
    "UserPreferencesUpdate",
    "UserRead",
]
