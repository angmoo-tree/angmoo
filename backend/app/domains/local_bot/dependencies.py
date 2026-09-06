from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.authorization import AuthorizationHeader, _bearer_token
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.local_bot.contracts.actions import LocalBotWorkflows
from app.domains.local_bot.contracts.authentication import (
    LocalBotAuthenticationWorkflows,
    LocalBotContext,
)
from app.domains.local_bot.contracts.key_management import LocalKeyWorkflows
from app.domains.local_bot.exceptions import (
    LocalBotAuthError,
    LocalBotForbiddenError,
    LocalBotModeError,
)
from app.domains.local_bot.service.authentication import authenticate_local_bot


def get_local_key_workflows(request: Request) -> LocalKeyWorkflows:
    factory = getattr(request.app.state, "local_key_workflows", None)
    if not callable(factory):
        raise RuntimeError("LocalBot key workflows are not configured")
    return factory()


def get_bot_workflows(request: Request) -> LocalBotWorkflows:
    factory = getattr(request.app.state, "local_bot_workflows", None)
    if not callable(factory):
        raise RuntimeError("LocalBot workflows are not configured")
    return factory()


def get_authentication_workflows(request: Request) -> LocalBotAuthenticationWorkflows:
    factory = getattr(request.app.state, "local_bot_authentication_workflows", None)
    if not callable(factory):
        raise RuntimeError("LocalBot authentication workflows are not configured")
    return factory()


def get_current_local_bot(
    authorization: AuthorizationHeader = None,
    db: Session = Depends(get_db),
    workflows: LocalBotAuthenticationWorkflows = Depends(get_authentication_workflows),
) -> LocalBotContext:
    token = _bearer_token(authorization)
    try:
        return authenticate_local_bot(db, token, workflows=workflows)
    except LocalBotAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except LocalBotForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except LocalBotModeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
