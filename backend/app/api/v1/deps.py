from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.core import browser_session
from app.core.db import get_db
from app.services import auth as auth_service
from app.services import demo_lock
from app.services import local_bot as local_bot_service


AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


@dataclass(frozen=True)
class AuthenticatedSessionContext:
    user: models.User
    session: models.AuthSession
    cookie_authenticated: bool


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
    _ensure_demo_request_allowed(context.user, context.session, request)
    return context.user


def resolve_authenticated_session_context(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> AuthenticatedSessionContext:
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


def get_current_admin_user(
    request: Request,
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> models.User:
    context = resolve_authenticated_session_context(request, authorization, db)
    user = context.user
    session = context.session
    try:
        demo_lock.ensure_demo_admin_access_allowed(
            user,
            auth_method=session.auth_method,
        )
    except demo_lock.DemoAccountLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    if session.auth_method != "google":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_google_login_required",
        )
    return user


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
        return None
    context = _resolve_session_context(
        request,
        db,
        token=token,
        cookie_authenticated=cookie_authenticated,
    )
    if context is None:
        return None
    _ensure_demo_request_allowed(context.user, context.session, request)
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
    )


def _ensure_demo_request_allowed(
    user: models.User,
    session: models.AuthSession,
    request: Request,
) -> None:
    try:
        demo_lock.ensure_demo_request_allowed(
            user,
            auth_method=session.auth_method,
            method=request.method,
        )
    except demo_lock.DemoAccountLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


def get_current_local_bot(
    authorization: AuthorizationHeader = None, db: Session = Depends(get_db)
) -> local_bot_service.LocalBotContext:
    token = _bearer_token(authorization)
    try:
        return local_bot_service.authenticate_local_bot(db, token)
    except local_bot_service.LocalBotAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except local_bot_service.LocalBotForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except local_bot_service.LocalBotModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


__all__ = [
    "AuthenticatedSessionContext",
    "get_current_admin_user",
    "get_current_local_bot",
    "get_current_session_for_logout",
    "get_current_user",
    "get_current_user_allow_incomplete",
    "get_optional_current_user",
    "resolve_authenticated_session_context",
    "get_db",
]
