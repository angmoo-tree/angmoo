from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.core.db import get_db
from app.services import auth as auth_service
from app.services import demo_lock
from app.services import local_bot as local_bot_service


AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


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
    result = auth_service.get_user_session_for_token(
        db,
        _bearer_token(authorization),
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    user, session = result
    _ensure_demo_request_allowed(user, session, request)
    return user


def get_current_session_for_logout(
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
) -> models.AuthSession:
    session = auth_service.get_session_for_token(
        db,
        _bearer_token(authorization),
    )
    if session is None or session.user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return session


def get_current_admin_user(
    authorization: AuthorizationHeader = None, db: Session = Depends(get_db)
) -> models.User:
    result = auth_service.get_user_session_for_token(db, _bearer_token(authorization))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    user, session = result
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
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    result = auth_service.get_user_session_for_token(db, token.strip())
    if result is None:
        return None
    user, session = result
    _ensure_demo_request_allowed(user, session, request)
    return user


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
    "get_current_admin_user",
    "get_current_local_bot",
    "get_current_session_for_logout",
    "get_current_user",
    "get_current_user_allow_incomplete",
    "get_optional_current_user",
    "get_db",
]
