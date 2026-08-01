from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
