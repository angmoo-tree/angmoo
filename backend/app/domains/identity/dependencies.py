from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.domains.identity import (
    models,
    browser_session,
)
from app.core.db import get_db
from app.core.desktop_loopback import is_authenticated_desktop_webview_request
from app.domains.identity.contracts import AccountDeletionWorkflow
from app.domains.identity.service import (
    auth as auth_service,
    demo_access as demo_lock,
)


AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


@dataclass(frozen=True)
class AuthenticatedSessionContext:
    user: models.User
    session: models.AuthSession | None
    cookie_authenticated: bool
    auth_method: str


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required"
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )
    return token.strip()


def get_current_user(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> models.User:
    user = get_current_user_allow_incomplete(request, authorization, db)
    if not user.profile_setup_completed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="profile_setup_required",
        )
    return user


def get_current_user_allow_incomplete(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> models.User:
    context = resolve_authenticated_session_context(request, authorization, db)
    _ensure_demo_request_allowed(context.user, context.auth_method, request)
    return context.user


def resolve_authenticated_session_context(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> AuthenticatedSessionContext:
    if (
        browser_session.session_cookie_token(request) is None
        and authorization is None
        and is_authenticated_desktop_webview_request(request)
    ):
        context = _resolve_desktop_owner_context(db)
        if context is not None:
            return context
    token, cookie_authenticated = _user_token_from_request(request, authorization)
    context = _resolve_session_context(
        request,
        db,
        token=token,
        cookie_authenticated=cookie_authenticated,
    )
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return context


def get_current_session_for_logout(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> models.AuthSession | None:
    token, cookie_authenticated = _user_token_from_request(
        request,
        authorization,
    )
    browser_session.require_cookie_mutation_origin(
        request,
        cookie_authenticated=cookie_authenticated,
    )
    session = auth_service.get_session_for_token(
        db,
        token,
    )
    if session is None or session.user.deleted_at is not None:
        if cookie_authenticated:
            return None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return session


def get_optional_current_user(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> models.User | None:
    cookie_token = browser_session.session_cookie_token(request)
    if cookie_token and authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ambiguous_auth",
        )
    if cookie_token:
        token = cookie_token
        cookie_authenticated = True
    elif authorization:
        scheme, _, bearer = authorization.partition(" ")
        if scheme.lower() != "bearer" or not bearer.strip():
            return None
        token = bearer.strip()
        cookie_authenticated = False
    else:
        if is_authenticated_desktop_webview_request(request):
            context = _resolve_desktop_owner_context(db)
            if context is not None:
                _ensure_demo_request_allowed(
                    context.user,
                    context.auth_method,
                    request,
                )
                return context.user
        return None
    context = _resolve_session_context(
        request,
        db,
        token=token,
        cookie_authenticated=cookie_authenticated,
    )
    if context is None:
        return None
    _ensure_demo_request_allowed(context.user, context.auth_method, request)
    return context.user


def _user_token_from_request(
    request: Request,
    authorization: str | None,
) -> tuple[str, bool]:
    cookie_token = browser_session.session_cookie_token(request)
    if cookie_token and authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ambiguous_auth",
        )
    if cookie_token:
        return cookie_token, True
    return _bearer_token(authorization), False


def _resolve_session_context(
    request: Request,
    db: Session,
    *,
    token: str,
    cookie_authenticated: bool,
) -> AuthenticatedSessionContext | None:
    result = auth_service.get_user_session_for_token(db, token)
    if result is None:
        return None
    user, session = result
    browser_session.require_cookie_mutation_origin(
        request,
        cookie_authenticated=cookie_authenticated,
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        cookie_authenticated=cookie_authenticated,
        auth_method=session.auth_method,
    )


def _resolve_desktop_owner_context(
    db: Session,
) -> AuthenticatedSessionContext | None:
    installation = db.get(models.InstallationIdentity, "local-installation")
    if (
        installation is None
        or installation.bootstrap_state != "claimed"
        or installation.owner_user_id is None
    ):
        return None
    user = db.get(models.User, installation.owner_user_id)
    if user is None or user.deleted_at is not None:
        return None
    return AuthenticatedSessionContext(
        user=user,
        session=None,
        cookie_authenticated=False,
        auth_method="local_owner",
    )


def _ensure_demo_request_allowed(
    user: models.User,
    auth_method: str,
    request: Request,
) -> None:
    try:
        demo_lock.ensure_demo_request_allowed(
            user,
            auth_method=auth_method,
            method=request.method,
        )
    except demo_lock.DemoAccountLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


__all__ = [
    "AuthenticatedSessionContext",
    "get_account_deletion_workflow",
    "get_current_session_for_logout",
    "get_current_user",
    "get_current_user_allow_incomplete",
    "get_optional_current_user",
    "resolve_authenticated_session_context",
    "get_db",
]


def get_account_deletion_workflow(request: Request) -> AccountDeletionWorkflow:
    """Resolve the workflow installed by the application composition."""
    workflow = getattr(request.app.state, "account_deletion_workflow", None)
    if not callable(workflow):
        raise RuntimeError("account deletion workflow is not configured")
    return workflow
