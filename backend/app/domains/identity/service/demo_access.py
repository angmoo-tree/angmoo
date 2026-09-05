from app.domains.identity import models
from app.config import settings


DEMO_ACCOUNT_LOCKED_MESSAGE = "Demo account is locked for portfolio review."
SAFE_DEMO_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


from app.domains.identity.exceptions import DemoAccountLockedError


def is_locked_demo_user(user: models.User) -> bool:
    email = (getattr(user, "email", None) or "").strip().lower()
    return email in settings.locked_demo_user_emails


def is_read_only_demo_principal(
    user: models.User,
    *,
    auth_method: str | None,
) -> bool:
    normalized_auth_method = (auth_method or "").strip().lower()
    return normalized_auth_method == "demo" or is_locked_demo_user(user)


def ensure_demo_request_allowed(
    user: models.User,
    *,
    auth_method: str | None,
    method: str,
) -> None:
    if (
        is_read_only_demo_principal(user, auth_method=auth_method)
        and method.strip().upper() not in SAFE_DEMO_HTTP_METHODS
    ):
        raise DemoAccountLockedError(DEMO_ACCOUNT_LOCKED_MESSAGE)


def ensure_demo_admin_access_allowed(
    user: models.User,
    *,
    auth_method: str | None,
) -> None:
    if is_read_only_demo_principal(user, auth_method=auth_method):
        raise DemoAccountLockedError(DEMO_ACCOUNT_LOCKED_MESSAGE)


def ensure_demo_user_mutable(user: models.User) -> None:
    if is_locked_demo_user(user):
        raise DemoAccountLockedError(DEMO_ACCOUNT_LOCKED_MESSAGE)
