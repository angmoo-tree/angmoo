from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.domains.identity import browser_session
from app.config import settings
from app.database import get_db
from app.domains.identity.schemas import (
    LocalBootstrapChallengeRead,
    LocalBootstrapRead,
    auth_read,
    bootstrap_read,
    AuthRead,
)
from app.domains.identity.exceptions import (
    BootstrapClosedError,
    LocalIdentityError,
    LocalOwnerProfileInvalidError,
)
from app.domains.identity.service.local_owner import LocalIdentityService
from app.domains.identity.schemas_local_entry import LocalClaimRequest, LocalClientQuery, LocalClientRequest, LocalClientRead, LocalPrepareRequest, LocalLabelUpdate
from app.domains.identity.service.local_entry import LocalEntryError, LocalEntryService, has_existing_owner_data
from app.core.sqlite_concurrency import SqliteConcurrencyError
from app.core import security
from app.domains.identity.models import AuthSession, LocalClientConnection, InstallationIdentity
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY


router = APIRouter(prefix="/auth/local", tags=["auth"])


from app.domains.identity.dependencies import get_authenticated_user_context_allow_incomplete, AuthenticatedSessionContext
from app.domains.identity.schemas_environment import EnvironmentRead, EnvironmentReport
from app.domains.identity.service.environment import EnvironmentConflict, EnvironmentTemporarilyBusy, read_environment, report_environment


@router.get("/environment", response_model=EnvironmentRead)
def get_environment(request: Request, db: Session = Depends(get_db),
                    context: AuthenticatedSessionContext = Depends(get_authenticated_user_context_allow_incomplete)):
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        return read_environment(db, context.user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/environment", response_model=EnvironmentRead)
def synchronize_environment(data: EnvironmentReport, request: Request, db: Session = Depends(get_db),
                            context: AuthenticatedSessionContext = Depends(get_authenticated_user_context_allow_incomplete)):
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return report_environment(db, context.user.id, data,
            session_hash=context.session.token_hash if context.session else None)
    except EnvironmentConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EnvironmentTemporarilyBusy as exc:
        raise HTTPException(status_code=503, detail="environment_temporarily_busy", headers={"Retry-After": "1"}) from exc
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/bootstrap", response_model=LocalBootstrapRead)
def get_local_bootstrap_status(
    request: Request,
    db: Session = Depends(get_db),
) -> LocalBootstrapRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    result = LocalIdentityService(db).get_bootstrap_status()
    output = bootstrap_read(result)
    output.automatic_prepare_allowed = result.state == "unclaimed" and not has_existing_owner_data(db)
    token = browser_session.session_cookie_token(request)
    session = db.get(AuthSession, security.hash_token(token)) if token else None
    client = db.get(LocalClientConnection, session.local_client_id) if session and session.local_client_id else None
    if client and client.installation_id == result.installation_id:
        output.client_connection = LocalClientRead(installation_id=client.installation_id,
            client_instance_id=client.client_instance_id, generation=client.generation, state=client.state).model_dump()
    return output


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
    data: LocalClaimRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthRead:
    prepare = LocalPrepareRequest(**data.model_dump(exclude={"owner_user_id", "local_label"}))
    return _prepare(prepare, request, response, db, owner_user_id=data.owner_user_id, local_label=data.local_label)


@router.post("/bootstrap/prepare", response_model=AuthRead)
def prepare_local_owner(data: LocalPrepareRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return _prepare(data, request, response, db)


def _prepare(data, request, response, db, **selection):
    browser_session.require_local_frontend_request(request, mutation=True)
    challenge = browser_session.bootstrap_challenge_cookie_token(request)
    if not challenge:
        raise HTTPException(status_code=401, detail="bootstrap_challenge_invalid")
    issued = _entry_call(lambda: LocalEntryService(db).prepare(data, challenge_token=challenge,
        secret_ready=bool(settings.app_secret.strip()), **selection))
    browser_session.delete_bootstrap_challenge_cookie(response)
    return _issued(response, issued)


@router.post("/session", response_model=AuthRead)
def issue_local_session(
    request: Request,
    response: Response,
    data: LocalClientRequest | None = None,
    db: Session = Depends(get_db),
) -> AuthRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    if data is None:
        raise HTTPException(status_code=409, detail="local_auth_contract_mismatch")
    issued = _entry_call(lambda: LocalEntryService(db).issue(data,
        secret_ready=bool(settings.app_secret.strip()), current_token=browser_session.session_cookie_token(request)))
    return _issued(response, issued)


@router.get("/client", response_model=LocalClientRead)
def local_client(request: Request, data: Annotated[LocalClientQuery, Query()], db: Session = Depends(get_db)):
    browser_session.require_local_frontend_request(request, mutation=False)
    return _entry_call(lambda: LocalEntryService(db).status(data))


@router.post("/client/stop", response_model=LocalClientRead)
def stop_local_client(data: LocalClientRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    browser_session.require_local_frontend_request(request, mutation=True)
    result = _entry_call(lambda: LocalEntryService(db).stop(data, current_token=browser_session.session_cookie_token(request)))
    browser_session.delete_session_cookie(response)
    return result


@router.post("/client/resume", response_model=AuthRead | LocalClientRead)
def resume_local_client(data: LocalClientRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    browser_session.require_local_frontend_request(request, mutation=True)
    issued = _entry_call(lambda: LocalEntryService(db).resume(data, secret_ready=bool(settings.app_secret.strip())))
    if isinstance(issued, LocalClientRead):
        return issued
    return _issued(response, issued)


@router.patch("/installation")
def update_installation(data: LocalLabelUpdate, request: Request, db: Session = Depends(get_db),
                        context: AuthenticatedSessionContext = Depends(get_authenticated_user_context_allow_incomplete)):
    browser_session.require_local_frontend_request(request, mutation=True)
    identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
    if identity is None or identity.bootstrap_state != "claimed" or identity.owner_user_id != context.user.id:
        raise HTTPException(status_code=403, detail="local_owner_required")
    owner_id, installation_id = context.user.id, identity.installation_id
    db.rollback()  # Close authenticated reads before the service-owned writer.
    return _entry_call(lambda: LocalEntryService(db).update_label(
        installation_id=installation_id, owner_id=owner_id, label=data.local_label))


def _entry_call(operation):
    try:
        return operation()
    except LocalEntryError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code,
            headers={"Retry-After": "1"} if exc.status in (429, 503) else None) from exc
    except LocalOwnerProfileInvalidError as exc:
        raise _identity_error(422, exc) from exc
    except SqliteConcurrencyError as exc:
        raise HTTPException(status_code=503, detail="local_session_temporarily_busy", headers={"Retry-After": "1"}) from exc


def _issued(response, issued):
    browser_session.set_session_cookie(
        response,
        issued.token,
        max_age_seconds=browser_session.seconds_until(issued.expires_at),
    )
    return auth_read(issued)


def _identity_error(status_code: int, error: LocalIdentityError) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error.code)
