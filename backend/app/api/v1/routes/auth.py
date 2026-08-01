from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import (
    get_current_session_for_logout,
    get_current_user_allow_incomplete,
    get_db,
)
from app.core import browser_session
from app.core.config import settings
from app.services import auth as auth_service
from app.services import demo_lock
from app.services import login_throttle
from app.services import turnstile


router = APIRouter(prefix="/auth", tags=["auth"])
public_router = APIRouter(prefix="/auth", tags=["auth"])
hosted_router = APIRouter(prefix="/auth", tags=["auth"])


def _browser_auth_response(
    response: Response,
    issued: auth_service.IssuedAuthSession,
) -> schemas.AuthRead:
    browser_session.set_session_cookie(response, issued.token)
    browser_session.delete_google_pending_cookie(response)
    return issued.public_response()


def _browser_google_response(
    response: Response,
    result: auth_service.GoogleLoginResult,
) -> schemas.GoogleLoginRead:
    if result.token:
        browser_session.set_session_cookie(response, result.token)
        browser_session.delete_google_pending_cookie(response)
    elif result.pending_token:
        browser_session.set_google_pending_cookie(response, result.pending_token)
    return result.public_response()


def _expired_google_signup_response() -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Invalid or expired signup token"},
    )
    browser_session.delete_google_pending_cookie(response)
    return response


def _verify_turnstile(token: str | None) -> None:
    try:
        turnstile.verify_turnstile_or_raise(token)
    except turnstile.TurnstileVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="turnstile_verification_failed",
        ) from exc
    except (
        turnstile.TurnstileConfigError,
        turnstile.TurnstileUnavailableError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="turnstile_unavailable",
        ) from exc


@router.post("/signup", response_model=schemas.AuthRead, status_code=status.HTTP_201_CREATED)
@hosted_router.post(
    "/signup",
    response_model=schemas.AuthRead,
    status_code=status.HTTP_201_CREATED,
)
def signup(
    data: schemas.SignupCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> schemas.AuthRead:
    browser_session.require_browser_origin(request)
    if not settings.password_signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="회원가입이 잠시 닫혀 있습니다.",
        )
    _verify_turnstile(data.turnstile_token)
    try:
        return _browser_auth_response(response, auth_service.create_user(db, data))
    except auth_service.EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        ) from exc
    except auth_service.DisplayNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 닉네임입니다.",
        ) from exc
    except auth_service.ReservedDisplayNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="공식 닉네임은 사용할 수 없습니다.",
        ) from exc
    except auth_service.DisplayNameBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="사용할 수 없는 닉네임입니다.",
        ) from exc
    except auth_service.DisplayNameInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="닉네임을 입력해주세요.",
        ) from exc
    except auth_service.PolicyAgreementRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="개인정보처리방침과 이용약관에 동의해주세요.",
        ) from exc
    except auth_service.DisplayNameCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="닉네임은 하루에 한 번만 변경할 수 있습니다.",
        ) from exc


@router.post("/login", response_model=schemas.AuthRead)
@public_router.post("/login", response_model=schemas.AuthRead)
def login(
    data: schemas.LoginCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> schemas.AuthRead:
    browser_session.require_browser_origin(request)
    try:
        return _browser_auth_response(
            response,
            auth_service.login(
                db,
                data,
                source=login_throttle.request_source(request),
            ),
        )
    except auth_service.LoginRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Login temporarily rate limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from exc


@router.post("/demo-login", response_model=schemas.AuthRead)
@public_router.post("/demo-login", response_model=schemas.AuthRead)
def demo_login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> schemas.AuthRead:
    browser_session.require_browser_origin(request)
    try:
        return _browser_auth_response(response, auth_service.login_demo(db))
    except auth_service.DemoLoginDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo login is not enabled",
        ) from exc
    except auth_service.DemoLoginUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo login is unavailable",
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@public_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    session: models.AuthSession | None = Depends(get_current_session_for_logout),
) -> Response:
    if session is not None:
        auth_service.revoke_current_session(db, session)
    browser_session.delete_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/google", response_model=schemas.GoogleLoginRead)
@public_router.post("/google", response_model=schemas.GoogleLoginRead)
def google_login(
    data: schemas.GoogleLoginCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> schemas.GoogleLoginRead:
    browser_session.require_browser_origin(request)
    try:
        return _browser_google_response(
            response,
            auth_service.login_with_google(
                db,
                data,
                source=login_throttle.request_source(request),
            ),
        )
    except auth_service.GoogleLoginRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Google login temporarily rate limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except auth_service.GoogleAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured",
        ) from exc
    except auth_service.InvalidGoogleCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google login",
        ) from exc
    except (
        auth_service.GoogleEmailAlreadyExistsError,
        auth_service.EmailAlreadyExistsError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 이메일입니다. 기존 로그인 방식으로 들어가거나 운영자에게 문의해 주세요.",
        ) from exc


@router.post("/google/complete", response_model=schemas.AuthRead)
@public_router.post("/google/complete", response_model=schemas.AuthRead)
def complete_google_signup(
    data: schemas.GoogleSignupCompleteCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> schemas.AuthRead | Response:
    browser_session.require_browser_origin(request)
    pending_token = browser_session.google_pending_cookie_token(request)
    if pending_token is None:
        return _expired_google_signup_response()
    _verify_turnstile(data.turnstile_token)
    try:
        return _browser_auth_response(
            response,
            auth_service.complete_google_signup(
                db,
                data,
                pending_token=pending_token,
            ),
        )
    except auth_service.InvalidGoogleSignupTokenError:
        return _expired_google_signup_response()
    except auth_service.PolicyAgreementRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="개인정보처리방침과 이용약관에 동의해주세요.",
        ) from exc
    except (
        auth_service.GoogleEmailAlreadyExistsError,
        auth_service.EmailAlreadyExistsError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 이메일입니다. 기존 로그인 방식으로 들어가거나 운영자에게 문의해 주세요.",
        ) from exc
    except auth_service.DisplayNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 닉네임입니다.",
        ) from exc
    except auth_service.DisplayNameBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="사용할 수 없는 닉네임입니다.",
        ) from exc
    except auth_service.ReservedDisplayNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="공식 닉네임은 사용할 수 없습니다.",
        ) from exc
    except auth_service.DisplayNameInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="닉네임을 입력해주세요.",
        ) from exc


@router.post("/google/link", response_model=schemas.AuthRead)
@public_router.post("/google/link", response_model=schemas.AuthRead)
def link_google_account(
    data: schemas.GoogleLinkCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_allow_incomplete),
) -> schemas.AuthRead:
    try:
        return _browser_auth_response(
            response,
            auth_service.link_google_account(
                db,
                user,
                data,
                source=login_throttle.request_source(request),
            ),
        )
    except auth_service.GoogleLoginRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Google login temporarily rate limited",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except auth_service.GoogleAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured",
        ) from exc
    except auth_service.InvalidGoogleCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google login",
        ) from exc
    except auth_service.GoogleLinkEmailMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google account email does not match current account",
        ) from exc
    except auth_service.GoogleSubAlreadyLinkedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google account is already linked to another user",
        ) from exc


@router.get("/me", response_model=schemas.UserRead)
@public_router.get("/me", response_model=schemas.UserRead)
def me(
    user: models.User = Depends(get_current_user_allow_incomplete),
) -> schemas.UserRead:
    return schemas.UserRead.model_validate(user)


@router.patch("/me", response_model=schemas.UserRead)
@public_router.patch("/me", response_model=schemas.UserRead)
def update_me(
    data: schemas.UserDisplayNameUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_allow_incomplete),
) -> schemas.UserRead:
    try:
        return auth_service.update_user_display_name(db, user, data)
    except auth_service.DisplayNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 닉네임입니다.",
        ) from exc
    except auth_service.DisplayNameBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="사용할 수 없는 닉네임입니다.",
        ) from exc
    except auth_service.ReservedDisplayNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="공식 닉네임은 사용할 수 없습니다.",
        ) from exc
    except auth_service.DisplayNameInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="닉네임을 입력해주세요.",
        ) from exc
    except auth_service.PolicyAgreementRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="개인정보처리방침과 이용약관에 동의해주세요.",
        ) from exc


@router.patch("/me/preferences", response_model=schemas.UserRead)
@public_router.patch("/me/preferences", response_model=schemas.UserRead)
def update_me_preferences(
    data: schemas.UserPreferencesUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_allow_incomplete),
) -> schemas.UserRead:
    return auth_service.update_user_preferences(db, user, data)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@public_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    data: schemas.AccountDeletionCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_allow_incomplete),
) -> Response:
    try:
        auth_service.delete_current_user_account(db, user, data)
    except auth_service.AccountDeletionConfirmationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="확인 문구가 일치하지 않습니다.",
        ) from exc
    except auth_service.AccountDeletionBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="앵무 활동이 진행 중이라 탈퇴할 수 없습니다. 잠시 뒤 다시 시도해주세요.",
        ) from exc
    except auth_service.AccountDeletionCredentialSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="탈퇴 전 보안 자격 정리에 실패했습니다. 잠시 뒤 다시 시도해주세요.",
        ) from exc
    except auth_service.AccountDeletionMediaCleanupError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="계정의 비공개 미디어 정리에 실패했습니다. 잠시 뒤 다시 시도해주세요.",
        ) from exc
    except demo_lock.DemoAccountLockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    browser_session.delete_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
