from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.domains.identity.dependencies import AuthorizationHeader, _bearer_token
from app.services import local_bot as local_bot_service


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
