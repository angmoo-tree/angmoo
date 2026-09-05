from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.domains.identity import browser_session
from app.config import settings
from app.core.db import get_db
from app.domains.identity.schemas import (
    LocalBootstrapChallengeRead,
    LocalBootstrapRead,
    LocalOwnerClaimCreate,
    auth_read,
    bootstrap_read,
    AuthRead,
)
from app.domains.identity.exceptions import (
    BootstrapChallengeInvalidError,
    BootstrapClosedError,
    BootstrapRaceLostError,
    LocalIdentityError,
    LocalOwnerCandidateInvalidError,
    LocalOwnerPrivacyAcknowledgementRequiredError,
    LocalOwnerProfileInvalidError,
    LocalOwnerUnclaimedError,
    LocalSessionRateLimitedError,
    LocalSessionUnavailableError,
)
from app.domains.identity.service.local_owner import LocalIdentityService


router = APIRouter(prefix="/auth/local", tags=["auth"])


@router.get("/bootstrap", response_model=LocalBootstrapRead)
def get_local_bootstrap_status(
    request: Request,
    db: Session = Depends(get_db),
) -> LocalBootstrapRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    result = LocalIdentityService(db).get_bootstrap_status()
    return bootstrap_read(result)


@router.post(
    "/bootstrap/challenge",
    response_model=LocalBootstrapChallengeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_local_bootstrap_challenge(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LocalBootstrapChallengeRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        issued = LocalIdentityService(db).create_bootstrap_challenge()
    except BootstrapClosedError as exc:
        raise _identity_error(status.HTTP_409_CONFLICT, exc) from exc
    browser_session.set_bootstrap_challenge_cookie(
        response,
        issued.token,
        max_age_seconds=browser_session.seconds_until(issued.expires_at),
    )
    return LocalBootstrapChallengeRead(expires_at=issued.expires_at)


@router.post(
    "/bootstrap/claim",
    response_model=AuthRead,
    status_code=status.HTTP_201_CREATED,
)
def claim_local_owner(
    data: LocalOwnerClaimCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    challenge_token = browser_session.bootstrap_challenge_cookie_token(request)
    if challenge_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bootstrap_challenge_invalid",
        )
    try:
        issued = LocalIdentityService(db).claim_local_owner(
            challenge_token=challenge_token,
            owner_user_id=data.owner_user_id,
            display_name=data.display_name,
            local_label=data.local_label,
            privacy_acknowledged=data.privacy_acknowledged,
        )
    except (BootstrapChallengeInvalidError,) as exc:
        raise _identity_error(status.HTTP_401_UNAUTHORIZED, exc) from exc
    except (BootstrapClosedError, BootstrapRaceLostError) as exc:
        raise _identity_error(status.HTTP_409_CONFLICT, exc) from exc
    except (
        LocalOwnerCandidateInvalidError,
        LocalOwnerProfileInvalidError,
        LocalOwnerPrivacyAcknowledgementRequiredError,
    ) as exc:
        raise _identity_error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc) from exc
    browser_session.set_session_cookie(
        response,
        issued.token,
        max_age_seconds=browser_session.seconds_until(issued.expires_at),
    )
    browser_session.delete_bootstrap_challenge_cookie(response)
    return auth_read(issued)


@router.post("/session", response_model=AuthRead)
def issue_local_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        issued = LocalIdentityService(db).issue_local_session(
            secret_ready=bool(settings.app_secret.strip()),
        )
    except LocalOwnerUnclaimedError as exc:
        raise _identity_error(status.HTTP_409_CONFLICT, exc) from exc
    except LocalSessionRateLimitedError as exc:
        raise _identity_error(status.HTTP_429_TOO_MANY_REQUESTS, exc) from exc
    except LocalSessionUnavailableError as exc:
        raise _identity_error(status.HTTP_503_SERVICE_UNAVAILABLE, exc) from exc
    browser_session.set_session_cookie(
        response,
        issued.token,
        max_age_seconds=browser_session.seconds_until(issued.expires_at),
    )
    return auth_read(issued)


def _identity_error(status_code: int, error: LocalIdentityError) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error.code)
