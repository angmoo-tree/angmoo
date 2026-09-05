import base64
import binascii
import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.integrations import google_identity
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.domains.identity import models, schemas
from app.core import security
from app.config import settings


from app.policies import name_policy
from app.domains.identity.service import (
    demo_access as demo_lock,
    external_verification as external_auth_verification,
    login_throttle,
)

from app.domains.identity.constants import (
    ACCOUNT_DELETE_CONFIRMATION,
    DELETED_USER_DISPLAY_NAME,
    DELETED_CHARACTER_NAME,
    DELETED_CHARACTER_PLACEHOLDER,
    OFFICIAL_OPERATOR_DISPLAY_NAME,
    OFFICIAL_OPERATOR_DISPLAY_NAME_KEY,
    LEGACY_ADMIN_DISPLAY_NAME_KEY,
    PRIVACY_POLICY_VERSION,
    TERMS_VERSION,
    GOOGLE_SIGNUP_PENDING_VERSION,
    GOOGLE_SIGNUP_PENDING_TTL,
    AUTH_SESSION_TTL,
    DUMMY_PASSWORD_HASH,
)
from app.domains.identity.exceptions import (
    AuthError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    LoginRateLimitedError,
    GoogleLoginRateLimitedError,
    GoogleAuthConfigError,
    InvalidGoogleCredentialError,
    GoogleEmailAlreadyExistsError,
    GoogleLinkEmailMismatchError,
    GoogleSubAlreadyLinkedError,
    InvalidGoogleSignupTokenError,
    PolicyAgreementRequiredError,
    DisplayNameAlreadyExistsError,
    DisplayNameInvalidError,
    ReservedDisplayNameError,
    DisplayNameBlockedError,
    DisplayNameCooldownError,
    AccountDeletionConfirmationError,
    AccountDeletionBusyError,
    AccountDeletionCredentialSyncError,
    AccountDeletionMediaCleanupError,
)
from app.domains.identity.contracts import AccountDeletionWorkflow


@dataclass(frozen=True)
class IssuedAuthSession:
    token: str
    user: schemas.UserRead
    profile_setup_required: bool = False
    expires_at: datetime | None = None

    def public_response(self) -> schemas.AuthRead:
        return schemas.AuthRead(
            user=self.user,
            profile_setup_required=self.profile_setup_required,
        )


@dataclass(frozen=True)
class GoogleLoginResult:
    token: str | None = None
    user: schemas.UserRead | None = None
    profile_setup_required: bool = False
    signup_required: bool = False
    pending_token: str | None = None
    expires_at: datetime | None = None
    email: str | None = None
    session_expires_at: datetime | None = None

    def public_response(self) -> schemas.GoogleLoginRead:
        return schemas.GoogleLoginRead(
            user=self.user,
            profile_setup_required=self.profile_setup_required,
            signup_required=self.signup_required,
            expires_at=self.expires_at,
            email=self.email,
        )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_display_name(display_name: str) -> str:
    return " ".join(display_name.strip().split())


def normalize_display_name_key(display_name: str) -> str:
    return normalize_display_name(display_name).casefold()


def create_user(db: Session, data: schemas.SignupCreate) -> IssuedAuthSession:
    _ensure_policy_agreements(data.privacy_policy_agreed, data.terms_agreed)
    email = normalize_email(data.email)
    existing = db.scalar(
        select(models.User).where(
            models.User.email == email,
            models.User.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise EmailAlreadyExistsError(email)
    display_name = normalize_display_name(data.display_name)
    display_name_normalized = normalize_display_name_key(display_name)
    if not display_name:
        raise DisplayNameInvalidError("Display name is required")
    _ensure_display_name_allowed(display_name, display_name_normalized)
    _ensure_display_name_available(db, display_name_normalized)

    now = _utcnow()
    user = models.User(
        id=f"user-{uuid4().hex[:12]}",
        email=email,
        password_hash=security.hash_password(data.password),
        display_name=display_name,
        display_name_normalized=display_name_normalized,
        display_name_updated_at=now,
        privacy_policy_agreed_at=now,
        terms_agreed_at=now,
        privacy_policy_version=PRIVACY_POLICY_VERSION,
        terms_version=TERMS_VERSION,
        profile_setup_completed=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_user_integrity_error(exc, email=email)
        raise EmailAlreadyExistsError(email) from exc
    db.refresh(user)
    return issue_auth_session(db, user)


def login(
    db: Session,
    data: schemas.LoginCreate,
    *,
    source: str = "unknown",
) -> IssuedAuthSession:
    email = normalize_email(data.email)
    throttle = login_throttle.lock_login_throttle(
        db,
        normalized_email=email,
        source=source,
    )
    retry_after_seconds = throttle.retry_after_seconds()
    if retry_after_seconds is not None:
        raise LoginRateLimitedError(retry_after_seconds)
    user = db.scalar(
        select(models.User).where(
            models.User.email == email,
            models.User.deleted_at.is_(None),
        )
    )
    password_hash = _password_hash_for_verification(user)
    password_matches = security.verify_password(data.password, password_hash)
    if user is None or user.password_hash is None or not password_matches:
        throttle.record_failure()
        login_throttle.cleanup_stale_buckets(db, now=throttle.now)
        db.commit()
        raise InvalidCredentialsError("Invalid email or password")
    throttle.reset_account_source()
    login_throttle.cleanup_stale_buckets(db, now=throttle.now)
    return issue_auth_session(db, user)


def login_with_google(
    db: Session,
    data: schemas.GoogleLoginCreate,
    *,
    source: str,
) -> GoogleLoginResult:
    try:
        reservation = external_auth_verification.reserve_google_verification(
            db,
            source=source,
        )
    except external_auth_verification.ExternalVerificationRateLimitedError as exc:
        raise GoogleLoginRateLimitedError(exc.retry_after_seconds) from exc

    try:
        payload = _verify_google_credential(data.credential)
    except InvalidGoogleCredentialError:
        external_auth_verification.complete_google_verification(
            db,
            reservation.id,
            outcome_class="invalid",
        )
        raise
    except Exception:
        external_auth_verification.complete_google_verification(
            db,
            reservation.id,
            outcome_class="error",
        )
        raise
    external_auth_verification.complete_google_verification(
        db,
        reservation.id,
        outcome_class="success",
    )
    google_sub = _required_payload_string(payload, "sub")
    email = normalize_email(_required_payload_string(payload, "email"))
    email_verified = payload.get("email_verified")
    if email_verified is not True and email_verified != "true":
        raise InvalidGoogleCredentialError("Google email is not verified")

    user = db.scalar(
        select(models.User).where(
            models.User.google_sub == google_sub,
            models.User.deleted_at.is_(None),
        )
    )
    if user is not None:
        return _google_login_from_auth(
            issue_auth_session(db, user, auth_method="google")
        )

    existing_email_user = db.scalar(
        select(models.User).where(
            models.User.email == email,
            models.User.deleted_at.is_(None),
        )
    )
    if existing_email_user is not None:
        raise GoogleEmailAlreadyExistsError(email)

    expires_at = _utcnow() + GOOGLE_SIGNUP_PENDING_TTL
    return GoogleLoginResult(
        signup_required=True,
        pending_token=_create_pending_google_signup_token(
            db,
            google_sub=google_sub,
            email=email,
            expires_at=expires_at,
        ),
        expires_at=expires_at,
        email=email,
    )


def complete_google_signup(
    db: Session,
    data: schemas.GoogleSignupCompleteCreate,
    *,
    pending_token: str,
) -> IssuedAuthSession:
    _ensure_policy_agreements(data.privacy_policy_agreed, data.terms_agreed)
    pending = _read_pending_google_signup_token(pending_token)
    grant = _lock_pending_google_signup_grant(
        db,
        jti=pending["jti"],
    )
    google_sub = pending["google_sub"]
    email = pending["email"]

    existing_google_user = db.scalar(
        select(models.User).where(
            models.User.google_sub == google_sub,
            models.User.deleted_at.is_(None),
        )
    )
    if existing_google_user is not None:
        grant.consumed_at = _utcnow()
        db.commit()
        return issue_auth_session(db, existing_google_user, auth_method="google")

    existing_email_user = db.scalar(
        select(models.User).where(
            models.User.email == email,
            models.User.deleted_at.is_(None),
        )
    )
    if existing_email_user is not None:
        raise GoogleEmailAlreadyExistsError(email)

    display_name = normalize_display_name(data.display_name)
    display_name_normalized = normalize_display_name_key(display_name)
    if not display_name:
        raise DisplayNameInvalidError("Display name is required")
    _ensure_display_name_allowed(display_name, display_name_normalized)
    _ensure_display_name_available(db, display_name_normalized)

    now = _utcnow()
    user = models.User(
        id=f"user-{uuid4().hex[:12]}",
        email=email,
        google_sub=google_sub,
        password_hash=None,
        display_name=display_name,
        display_name_normalized=display_name_normalized,
        display_name_updated_at=now,
        privacy_policy_agreed_at=now,
        terms_agreed_at=now,
        privacy_policy_version=PRIVACY_POLICY_VERSION,
        terms_version=TERMS_VERSION,
        profile_setup_completed=True,
    )
    db.add(user)
    grant.consumed_at = now
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_user_integrity_error(exc, email=email)
        raise GoogleEmailAlreadyExistsError(email) from exc
    db.refresh(user)
    return issue_auth_session(db, user, auth_method="google")


def link_google_account(
    db: Session,
    user: models.User,
    data: schemas.GoogleLinkCreate,
    *,
    source: str,
) -> IssuedAuthSession:
    try:
        reservation = external_auth_verification.reserve_google_verification(
            db,
            source=f"google-link:{user.id}:{source}",
        )
    except external_auth_verification.ExternalVerificationRateLimitedError as exc:
        raise GoogleLoginRateLimitedError(exc.retry_after_seconds) from exc

    try:
        payload = _verify_google_credential(data.credential)
    except InvalidGoogleCredentialError:
        external_auth_verification.complete_google_verification(
            db,
            reservation.id,
            outcome_class="invalid",
        )
        raise
    except Exception:
        external_auth_verification.complete_google_verification(
            db,
            reservation.id,
            outcome_class="error",
        )
        raise
    external_auth_verification.complete_google_verification(
        db,
        reservation.id,
        outcome_class="success",
    )
    google_sub = _required_payload_string(payload, "sub")
    email = normalize_email(_required_payload_string(payload, "email"))
    email_verified = payload.get("email_verified")
    if email_verified is not True and email_verified != "true":
        raise InvalidGoogleCredentialError("Google email is not verified")
    if normalize_email(user.email or "") != email:
        raise GoogleLinkEmailMismatchError(
            "Google email does not match current account"
        )
    existing_google_user = db.scalar(
        select(models.User).where(
            models.User.google_sub == google_sub,
            models.User.deleted_at.is_(None),
            models.User.id != user.id,
        )
    )
    if existing_google_user is not None:
        raise GoogleSubAlreadyLinkedError("Google account is already linked")
    user.google_sub = google_sub
    db.commit()
    db.refresh(user)
    return issue_auth_session(db, user, auth_method="google")


def update_user_display_name(
    db: Session, user: models.User, data: schemas.UserDisplayNameUpdate
) -> schemas.UserRead:
    display_name = normalize_display_name(data.display_name)
    display_name_normalized = normalize_display_name_key(display_name)
    if not display_name:
        raise DisplayNameInvalidError("Display name is required")
    if _is_same_display_name(user, display_name, display_name_normalized):
        return schemas.UserRead.model_validate(user)
    _ensure_display_name_allowed(display_name, display_name_normalized, user=user)
    _ensure_display_name_change_allowed(user)
    _ensure_display_name_available(db, display_name_normalized, exclude_user_id=user.id)

    now = _utcnow()
    if not user.profile_setup_completed and not _has_policy_agreements(user):
        _ensure_policy_agreements(
            data.privacy_policy_agreed is True,
            data.terms_agreed is True,
        )
        _set_policy_agreements(user, now)

    user.display_name = display_name
    user.display_name_normalized = display_name_normalized
    user.display_name_updated_at = now
    user.profile_setup_completed = True
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_user_integrity_error(exc, email=user.email)
        raise DisplayNameAlreadyExistsError(display_name) from exc
    db.refresh(user)
    return schemas.UserRead.model_validate(user)


def update_user_preferences(
    db: Session, user: models.User, data: schemas.UserPreferencesUpdate
) -> schemas.UserRead:
    user.feed_content_filter = data.feed_content_filter
    db.commit()
    db.refresh(user)
    return schemas.UserRead.model_validate(user)


def get_user_for_token(db: Session, token: str) -> models.User | None:
    session = get_session_for_token(db, token)
    if session is None:
        return None
    if session.user.deleted_at is not None:
        return None
    return session.user


def get_session_for_token(db: Session, token: str) -> models.AuthSession | None:
    session = db.get(models.AuthSession, security.hash_token(token))
    if session is None:
        return None

    expires_at = session.expires_at
    if expires_at is None:
        expires_at = _as_utc(session.created_at) + AUTH_SESSION_TTL
    else:
        expires_at = _as_utc(expires_at)
    if expires_at <= _utcnow():
        return None
    return session


def get_user_session_for_token(
    db: Session, token: str
) -> tuple[models.User, models.AuthSession] | None:
    session = get_session_for_token(db, token)
    if session is None or session.user.deleted_at is not None:
        return None
    return session.user, session


def revoke_current_session(db: Session, session: models.AuthSession) -> None:
    db.delete(session)
    db.commit()


def _google_login_from_auth(auth: IssuedAuthSession) -> GoogleLoginResult:
    return GoogleLoginResult(
        token=auth.token,
        user=auth.user,
        profile_setup_required=auth.profile_setup_required,
        session_expires_at=auth.expires_at,
    )


def _ensure_policy_agreements(privacy_policy_agreed: bool, terms_agreed: bool) -> None:
    if privacy_policy_agreed is not True or terms_agreed is not True:
        raise PolicyAgreementRequiredError("Policy agreements are required")


def _has_policy_agreements(user: models.User) -> bool:
    return (
        user.privacy_policy_agreed_at is not None and user.terms_agreed_at is not None
    )


def _set_policy_agreements(user: models.User, agreed_at: datetime) -> None:
    user.privacy_policy_agreed_at = agreed_at
    user.terms_agreed_at = agreed_at
    user.privacy_policy_version = PRIVACY_POLICY_VERSION
    user.terms_version = TERMS_VERSION


def _pending_signup_key() -> bytes:
    return hmac.new(
        settings.app_secret.encode("utf-8"),
        b"angmoo-google-signup-pending-key-v1",
        hashlib.sha256,
    ).digest()


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _create_pending_google_signup_token(
    db: Session,
    *,
    google_sub: str,
    email: str,
    expires_at: datetime,
) -> str:
    jti = uuid4().hex
    payload = {
        "google_sub": google_sub,
        "email": email,
        "exp": int(expires_at.timestamp()),
        "jti": jti,
    }
    payload_raw = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signed = f"{GOOGLE_SIGNUP_PENDING_VERSION}.{payload_raw}"
    signature = hmac.new(
        _pending_signup_key(),
        signed.encode("ascii"),
        hashlib.sha256,
    ).digest()
    now = _utcnow()
    db.execute(
        delete(models.AuthGoogleSignupGrant).where(
            models.AuthGoogleSignupGrant.expires_at < now - timedelta(hours=24)
        )
    )
    db.add(
        models.AuthGoogleSignupGrant(
            jti_hash=_pending_signup_jti_hash(jti),
            created_at=now,
            expires_at=expires_at,
            consumed_at=None,
        )
    )
    db.commit()
    return f"{signed}.{_b64url_encode(signature)}"


def _read_pending_google_signup_token(token: str) -> dict[str, str]:
    try:
        version, payload_raw, signature_raw = token.split(".", 2)
    except ValueError as exc:
        raise InvalidGoogleSignupTokenError("Invalid pending signup token") from exc
    if version != GOOGLE_SIGNUP_PENDING_VERSION:
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")

    signed = f"{version}.{payload_raw}"
    expected = hmac.new(
        _pending_signup_key(),
        signed.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        actual = _b64url_decode(signature_raw)
    except (binascii.Error, ValueError) as exc:
        raise InvalidGoogleSignupTokenError("Invalid pending signup token") from exc
    if not hmac.compare_digest(actual, expected):
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")

    try:
        payload = json.loads(_b64url_decode(payload_raw).decode("utf-8"))
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise InvalidGoogleSignupTokenError("Invalid pending signup token") from exc
    if not isinstance(payload, dict):
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")

    exp = payload.get("exp")
    google_sub = payload.get("google_sub")
    email = payload.get("email")
    jti = payload.get("jti")
    if not isinstance(exp, int) or exp <= int(_utcnow().timestamp()):
        raise InvalidGoogleSignupTokenError("Pending signup token expired")
    if not isinstance(google_sub, str) or not google_sub.strip():
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")
    if not isinstance(email, str) or not email.strip():
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")
    if not isinstance(jti, str) or not jti.strip():
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")
    return {
        "google_sub": google_sub.strip(),
        "email": normalize_email(email),
        "jti": jti.strip(),
    }


def _pending_signup_jti_hash(jti: str) -> str:
    return hmac.new(
        _pending_signup_key(),
        f"google-signup-jti-v1:{jti}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _lock_pending_google_signup_grant(
    db: Session,
    *,
    jti: str,
) -> models.AuthGoogleSignupGrant:
    grant = db.scalar(
        select(models.AuthGoogleSignupGrant)
        .where(models.AuthGoogleSignupGrant.jti_hash == _pending_signup_jti_hash(jti))
        .with_for_update()
    )
    now = _utcnow()
    if grant is None:
        db.rollback()
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")
    expires_at = grant.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if grant.consumed_at is not None or expires_at <= now:
        db.rollback()
        raise InvalidGoogleSignupTokenError("Invalid pending signup token")
    return grant


def issue_auth_session(
    db: Session,
    user: models.User,
    *,
    auth_method: str = "password",
    expires_at: datetime | None = None,
) -> IssuedAuthSession:
    normalized_expires_at = _as_utc(expires_at) if expires_at is not None else None
    if normalized_expires_at is not None and normalized_expires_at <= _utcnow():
        raise ValueError("auth session expiry must be in the future")
    token = security.create_token()
    db.add(
        models.AuthSession(
            token_hash=security.hash_token(token),
            user_id=user.id,
            auth_method=auth_method,
            expires_at=normalized_expires_at,
        )
    )
    db.commit()
    profile_setup_required = not user.profile_setup_completed
    return IssuedAuthSession(
        token=token,
        user=schemas.UserRead.model_validate(user),
        profile_setup_required=profile_setup_required,
        expires_at=normalized_expires_at,
    )


def auth_session_cookie_max_age(
    expires_at: datetime | None,
    *,
    now: datetime | None = None,
) -> int | None:
    if expires_at is None:
        return None
    remaining = (_as_utc(expires_at) - _as_utc(now or _utcnow())).total_seconds()
    return max(0, math.ceil(remaining))


def _create_auth_response(
    db: Session, user: models.User, *, auth_method: str = "password"
) -> IssuedAuthSession:
    """Compatibility wrapper for callers migrating to issue_auth_session."""
    return issue_auth_session(db, user, auth_method=auth_method)


def _password_hash_for_verification(user: models.User | None) -> str:
    if user is None or not _is_current_password_hash(user.password_hash):
        return DUMMY_PASSWORD_HASH
    return user.password_hash or DUMMY_PASSWORD_HASH


def _is_current_password_hash(password_hash: str | None) -> bool:
    if not password_hash:
        return False
    parts = password_hash.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4))
        base64.urlsafe_b64decode(parts[3] + "=" * (-len(parts[3]) % 4))
    except (ValueError, binascii.Error):
        return False
    return iterations == security.PASSWORD_ITERATIONS


def _verify_google_credential(credential: str) -> dict[str, object]:
    client_id = settings.google_oauth_client_id
    if client_id is None:
        raise GoogleAuthConfigError("Google OAuth client ID is not configured")
    try:
        payload = google_identity.verify_oauth2_token(credential, client_id)
    except (ValueError, google_identity.GoogleAuthError) as exc:
        raise InvalidGoogleCredentialError("Invalid Google credential") from exc
    if not isinstance(payload, dict):
        raise InvalidGoogleCredentialError("Invalid Google credential")
    return payload


def _required_payload_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidGoogleCredentialError("Invalid Google credential")
    return value.strip()


def _ensure_display_name_available(
    db: Session, display_name_normalized: str, *, exclude_user_id: str | None = None
) -> None:
    query = select(models.User).where(
        models.User.display_name_normalized == display_name_normalized
    )
    if exclude_user_id is not None:
        query = query.where(models.User.id != exclude_user_id)
    if db.scalar(query) is not None:
        raise DisplayNameAlreadyExistsError(display_name_normalized)


def _ensure_display_name_allowed(
    display_name: str,
    display_name_normalized: str,
    *,
    user: models.User | None = None,
) -> None:
    if display_name_normalized == OFFICIAL_OPERATOR_DISPLAY_NAME_KEY:
        if (
            user is not None
            and _is_official_operator_user(user)
            and display_name == OFFICIAL_OPERATOR_DISPLAY_NAME
        ):
            return
        raise ReservedDisplayNameError(display_name_normalized)

    if display_name_normalized == LEGACY_ADMIN_DISPLAY_NAME_KEY:
        raise ReservedDisplayNameError(display_name_normalized)

    _ensure_display_name_not_blocked(display_name)


def _is_official_operator_user(user: models.User) -> bool:
    return user.id in settings.official_operator_user_ids


def _ensure_display_name_not_blocked(display_name: str) -> None:
    if name_policy.is_blocked_name(display_name):
        raise DisplayNameBlockedError("display name is blocked by policy")


def _ensure_display_name_change_allowed(user: models.User) -> None:
    if not user.profile_setup_completed:
        return
    available_at = user.display_name_change_available_at
    if available_at is None:
        return
    if available_at > _utcnow():
        raise DisplayNameCooldownError(available_at)


def _is_same_display_name(
    user: models.User, display_name: str, display_name_normalized: str
) -> bool:
    current_display_name = normalize_display_name(user.display_name)
    current_normalized = user.display_name_normalized
    if current_normalized is None:
        current_normalized = normalize_display_name_key(current_display_name)
    return (
        user.profile_setup_completed
        and display_name == current_display_name
        and display_name_normalized == current_normalized
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _raise_user_integrity_error(exc: IntegrityError, *, email: str | None) -> None:
    message = str(exc.orig).lower()
    if "display_name_normalized" in message:
        raise DisplayNameAlreadyExistsError("display_name") from exc
    if "email" in message and email is not None:
        raise EmailAlreadyExistsError(email) from exc


def delete_current_user_account(
    db: Session, user: models.User, data: schemas.AccountDeletionCreate,
    *, workflow: AccountDeletionWorkflow,
) -> None:
    """Admit account deletion; the injected application workflow owns the UoW."""
    if data.confirmation != ACCOUNT_DELETE_CONFIRMATION:
        raise AccountDeletionConfirmationError("Confirmation text does not match")
    if user.deleted_at is not None:
        return
    demo_lock.ensure_demo_user_mutable(user)
    workflow(db, user)
