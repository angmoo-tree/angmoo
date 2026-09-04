import base64
import binascii
import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import delete, false, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core import security
from app.core.config import settings
from app.core.redaction import redact_secret_text
from app.cruds import agent_runs as agent_run_crud
from app.policies import name_policy
from app.services import (
    demo_lock,
    external_auth_verification,
    login_throttle,
    profile_media,
)
from app.services.runtime_boundary import (
    OpenClawGatewayClient,
    OpenClawGatewayError,
    openclaw_auth_profiles,
)


ACCOUNT_DELETE_CONFIRMATION = "회원탈퇴"
DELETED_USER_DISPLAY_NAME = "탈퇴한 사용자"
DELETED_CHARACTER_NAME = "삭제한 앵무"
DELETED_CHARACTER_PLACEHOLDER = "삭제된 앵무입니다."
OFFICIAL_OPERATOR_DISPLAY_NAME = "운영자"
OFFICIAL_OPERATOR_DISPLAY_NAME_KEY = "운영자"
LEGACY_ADMIN_DISPLAY_NAME_KEY = "관리자"
PRIVACY_POLICY_VERSION = "2026-06-22"
TERMS_VERSION = "2026-06-22"
GOOGLE_SIGNUP_PENDING_VERSION = "google-signup-v2"
GOOGLE_SIGNUP_PENDING_TTL = timedelta(minutes=15)
AUTH_SESSION_TTL = timedelta(days=7)
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$120000$YW5nbW9vLWxvZ2luLWR1bQ$"
    "E8qJt3gADSd29Q8eOxpm9d43BxgPMxclvxzfgyA7dL4"
)


class AuthError(Exception):
    pass


class EmailAlreadyExistsError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class LoginRateLimitedError(AuthError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Login temporarily rate limited")


class GoogleLoginRateLimitedError(AuthError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Google login temporarily rate limited")


class GoogleAuthConfigError(AuthError):
    pass


class InvalidGoogleCredentialError(AuthError):
    pass


class GoogleEmailAlreadyExistsError(AuthError):
    pass


class GoogleLinkEmailMismatchError(AuthError):
    pass


class GoogleSubAlreadyLinkedError(AuthError):
    pass


class InvalidGoogleSignupTokenError(AuthError):
    pass


class PolicyAgreementRequiredError(AuthError):
    pass


class DisplayNameAlreadyExistsError(AuthError):
    pass


class DisplayNameInvalidError(AuthError):
    pass


class ReservedDisplayNameError(AuthError):
    pass


class DisplayNameBlockedError(AuthError):
    pass


class DisplayNameCooldownError(AuthError):
    def __init__(self, available_at: datetime) -> None:
        self.available_at = available_at
        super().__init__("Display name change is on cooldown")


class AccountDeletionConfirmationError(AuthError):
    pass


class AccountDeletionBusyError(AuthError):
    pass


class AccountDeletionCredentialSyncError(AuthError):
    pass


class AccountDeletionMediaCleanupError(AuthError):
    pass


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


def delete_current_user_account(
    db: Session, user: models.User, data: schemas.AccountDeletionCreate
) -> None:
    if data.confirmation != ACCOUNT_DELETE_CONFIRMATION:
        raise AccountDeletionConfirmationError("Confirmation text does not match")
    if user.deleted_at is not None:
        return
    demo_lock.ensure_demo_user_mutable(user)

    characters = list(
        db.scalars(
            select(models.Character)
            .where(models.Character.owner_id == user.id)
            .order_by(models.Character.id.asc())
        )
    )
    character_ids = [character.id for character in characters]

    _ensure_account_deletion_not_busy(db, user.id, character_ids)
    media_quarantine = _quarantine_account_private_media(db, user.id, character_ids)
    try:
        _release_openclaw_profiles_for_account(db, user.id, character_ids)
        _clear_resident_slots_for_account(db, user.id, character_ids)
        db.flush()
        _scrub_account_data(db, user, characters, character_ids)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            media_quarantine.restore()
        except profile_media.PrivateMediaCleanupError as restore_exc:
            raise AccountDeletionMediaCleanupError(
                "private_media_restore_failed"
            ) from restore_exc
        if isinstance(exc, IntegrityError):
            raise AuthError("Account deletion failed") from exc
        raise
    try:
        media_quarantine.purge()
    except profile_media.PrivateMediaCleanupError as exc:
        raise AccountDeletionMediaCleanupError("private_media_purge_failed") from exc


def _quarantine_account_private_media(
    db: Session, user_id: str, character_ids: list[str]
) -> profile_media.PrivateMediaQuarantine:
    draft_ids = list(
        db.scalars(
            select(models.AgentCreationDraft.id).where(
                models.AgentCreationDraft.user_id == user_id
            )
        )
    )
    media_root = settings.media_root_path
    paths = [media_root / "characters" / character_id for character_id in character_ids]
    paths.extend(media_root / "drafts" / draft_id for draft_id in draft_ids)
    paths.append(media_root / "profile-candidates" / user_id)
    return profile_media.quarantine_private_media(paths)


def _ensure_account_deletion_not_busy(
    db: Session, user_id: str, character_ids: list[str]
) -> None:
    active_run_id = db.scalar(
        select(models.AgentRun.id)
        .where(
            _owned_agent_run_condition(user_id, character_ids),
            models.AgentRun.status.in_(agent_run_crud.ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    )
    if active_run_id is not None:
        raise AccountDeletionBusyError("Agent run is running")

    running_slot_id = db.scalar(
        select(models.AgentSlot.agent_id)
        .where(
            _owned_agent_slot_condition(user_id, character_ids),
            models.AgentSlot.status == agent_run_crud.SLOT_STATUS_RUNNING,
        )
        .limit(1)
    )
    if running_slot_id is not None:
        raise AccountDeletionBusyError("Resident slot is running")


def _release_openclaw_profiles_for_account(
    db: Session, user_id: str, character_ids: list[str]
) -> None:
    if settings.agent_activity_engine != "openclaw":
        return
    released = False
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(_owned_agent_slot_condition(user_id, character_ids))
            .order_by(models.AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == agent_run_crud.SLOT_STATUS_RUNNING:
            raise AccountDeletionBusyError("Resident slot is running")
        if (
            slot.assigned_user_id is None
            or slot.assigned_character_id is None
            or slot.assigned_credential_id is None
        ):
            continue
        credential = db.get(models.LlmCredential, slot.assigned_credential_id)
        if credential is None:
            continue
        try:
            openclaw_auth_profiles.release_credential_from_slot(
                agent_id=slot.agent_id,
                user_id=slot.assigned_user_id,
                character_id=slot.assigned_character_id,
                credential=credential,
            )
        except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
            raise AccountDeletionCredentialSyncError(
                redact_secret_text(str(exc))
            ) from exc
        released = True
    if released:
        _reload_openclaw_secrets_sync()


def _reload_openclaw_secrets_sync() -> None:
    token = settings.openclaw_gateway_token
    if token is None:
        return
    try:
        OpenClawGatewayClient(
            url=settings.openclaw_gateway_url,
            token=token,
            timeout_seconds=settings.openclaw_timeout_seconds,
        ).reload_secrets_sync()
    except OpenClawGatewayError as exc:
        raise AccountDeletionCredentialSyncError(redact_secret_text(str(exc))) from exc


def _clear_resident_slots_for_account(
    db: Session, user_id: str, character_ids: list[str]
) -> None:
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(_owned_agent_slot_condition(user_id, character_ids))
            .order_by(models.AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == agent_run_crud.SLOT_STATUS_RUNNING:
            raise AccountDeletionBusyError("Resident slot is running")
        slot.status = agent_run_crud.SLOT_STATUS_EMPTY
        slot.assigned_user_id = None
        slot.assigned_character_id = None
        slot.assigned_credential_id = None
        slot.next_tick_at = None
        slot.last_run_at = None
        slot.heartbeat_interval_seconds = None
        slot.locked_by_run_id = None
        slot.lease_expires_at = None
        slot.last_error = None


def _scrub_account_data(
    db: Session,
    user: models.User,
    characters: list[models.Character],
    character_ids: list[str],
) -> None:
    now = _utcnow()
    character_condition = _character_id_condition

    from app.services import world_character_setup

    from app.runtime.memory_privacy import scrub_memory_data

    scrub_memory_data(db, owner_id=user.id)
    db.execute(
        delete(models.SocialActionSubjectiveContext).where(
            models.SocialActionSubjectiveContext.owner_id == user.id
        )
    )
    world_character_setup.delete_setup_data_for_characters(
        db, character_ids=character_ids
    )

    db.execute(
        delete(models.ProfileImageCandidate).where(
            or_(
                models.ProfileImageCandidate.user_id == user.id,
                character_condition(
                    models.ProfileImageCandidate.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.ProfileImageQuotaReservation).where(
            models.ProfileImageQuotaReservation.user_id == user.id
        )
    )
    db.execute(
        delete(models.AgentCreationDraft).where(
            models.AgentCreationDraft.user_id == user.id
        )
    )

    message_thread_ids = select(models.MessageThread.id).where(
        or_(
            models.MessageThread.requester_id == user.id,
            character_condition(models.MessageThread.character_id, character_ids),
        )
    )
    db.execute(
        delete(models.MessageMessage).where(
            models.MessageMessage.thread_id.in_(message_thread_ids)
        )
    )
    db.execute(
        delete(models.MessageThread).where(
            or_(
                models.MessageThread.requester_id == user.id,
                character_condition(models.MessageThread.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.UserMessagePreference).where(
            models.UserMessagePreference.user_id == user.id
        )
    )
    db.execute(
        delete(models.CharacterMessageSetting).where(
            character_condition(
                models.CharacterMessageSetting.character_id, character_ids
            )
        )
    )

    lore_source_ids = select(models.CharacterLoreSource.id).where(
        or_(
            models.CharacterLoreSource.owner_id == user.id,
            character_condition(models.CharacterLoreSource.character_id, character_ids),
        )
    )
    db.execute(
        delete(models.CharacterLoreChunk).where(
            or_(
                models.CharacterLoreChunk.owner_id == user.id,
                character_condition(
                    models.CharacterLoreChunk.character_id, character_ids
                ),
                models.CharacterLoreChunk.source_id.in_(lore_source_ids),
            )
        )
    )
    db.execute(
        delete(models.CharacterLoreSource).where(
            or_(
                models.CharacterLoreSource.owner_id == user.id,
                character_condition(
                    models.CharacterLoreSource.character_id, character_ids
                ),
            )
        )
    )

    db.execute(
        delete(models.PostImageGenerationJob).where(
            or_(
                models.PostImageGenerationJob.user_id == user.id,
                character_condition(
                    models.PostImageGenerationJob.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.PostImageQuotaReservation).where(
            or_(
                models.PostImageQuotaReservation.user_id == user.id,
                character_condition(
                    models.PostImageQuotaReservation.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.AgentPublicActionExecution).where(
            character_condition(
                models.AgentPublicActionExecution.character_id, character_ids
            )
        )
    )
    db.execute(
        delete(models.AgentDaypartMemoryEvent).where(
            character_condition(
                models.AgentDaypartMemoryEvent.character_id, character_ids
            )
        )
    )
    db.execute(
        delete(models.AgentRelationshipPoint).where(
            or_(
                character_condition(
                    models.AgentRelationshipPoint.recipient_character_id,
                    character_ids,
                ),
                character_condition(
                    models.AgentRelationshipPoint.source_character_id,
                    character_ids,
                ),
            )
        )
    )

    db.execute(delete(models.AuthSession).where(models.AuthSession.user_id == user.id))
    db.execute(
        delete(models.AgentFeedCue).where(
            or_(
                models.AgentFeedCue.user_id == user.id,
                character_condition(models.AgentFeedCue.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.AgentActivityLog).where(
            or_(
                models.AgentActivityLog.user_id == user.id,
                character_condition(
                    models.AgentActivityLog.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.AgentRun).where(
            _owned_agent_run_condition(user.id, character_ids)
        )
    )
    db.execute(
        delete(models.PostReport).where(models.PostReport.reporter_user_id == user.id)
    )
    db.execute(
        delete(models.PostLike).where(
            or_(
                models.PostLike.user_id == user.id,
                character_condition(models.PostLike.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.PostRepost).where(
            or_(
                models.PostRepost.user_id == user.id,
                character_condition(models.PostRepost.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.ProfileFollow).where(
            or_(
                models.ProfileFollow.follower_user_id == user.id,
                models.ProfileFollow.target_user_id == user.id,
                character_condition(
                    models.ProfileFollow.follower_character_id, character_ids
                ),
                character_condition(
                    models.ProfileFollow.target_character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.Notification).where(
            or_(
                models.Notification.recipient_user_id == user.id,
                models.Notification.actor_user_id == user.id,
                character_condition(
                    models.Notification.recipient_character_id, character_ids
                ),
                character_condition(
                    models.Notification.actor_character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        update(models.Post)
        .where(models.Post.author_user_id == user.id)
        .values(author_name=DELETED_USER_DISPLAY_NAME)
    )
    if character_ids:
        db.execute(
            update(models.Post)
            .where(models.Post.author_character_id.in_(character_ids))
            .values(author_name=DELETED_CHARACTER_NAME)
        )
        db.execute(
            delete(models.CharacterState).where(
                models.CharacterState.character_id.in_(character_ids)
            )
        )
        db.execute(
            delete(models.AgentImageGenerationSetting).where(
                models.AgentImageGenerationSetting.character_id.in_(character_ids)
            )
        )

    db.execute(
        delete(models.AgentActivitySetting).where(
            character_condition(models.AgentActivitySetting.character_id, character_ids)
        )
    )

    db.execute(
        delete(models.LlmCredential).where(
            or_(
                models.LlmCredential.owner_id == user.id,
                character_condition(models.LlmCredential.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.AgentLocalKey).where(
            or_(
                models.AgentLocalKey.owner_id == user.id,
                character_condition(models.AgentLocalKey.character_id, character_ids),
            )
        )
    )
    db.execute(
        update(models.AdminAuditLog)
        .where(models.AdminAuditLog.admin_user_id == user.id)
        .values(note=None, metadata_json=None, request_ip=None, user_agent=None)
    )
    db.execute(
        update(models.SiteOperationBanner)
        .where(models.SiteOperationBanner.updated_by_user_id == user.id)
        .values(updated_by_user_id=None)
    )
    db.execute(
        update(models.SiteOperationSetting)
        .where(models.SiteOperationSetting.updated_by_user_id == user.id)
        .values(updated_by_user_id=None)
    )
    db.execute(
        update(models.Character)
        .where(models.Character.moderation_updated_by_user_id == user.id)
        .values(moderation_updated_by_user_id=None)
    )

    for character in characters:
        character.name = DELETED_CHARACTER_NAME
        character.handle = _deleted_character_handle(db, character.id)
        character.avatar_url = None
        character.banner_url = None
        character.one_liner = DELETED_CHARACTER_PLACEHOLDER
        character.personality = ""
        character.speech_style = ""
        character.worldview = ""
        character.topic_preferences = ""
        character.safety_rules = ""
        character.status = "inactive"
        character.persona_summary = DELETED_CHARACTER_PLACEHOLDER
        character.deleted_at = now

    user.email = None
    user.google_sub = None
    user.password_hash = None
    user.display_name = DELETED_USER_DISPLAY_NAME
    user.display_name_normalized = None
    user.display_name_updated_at = None
    user.is_admin = False
    user.privacy_policy_agreed_at = None
    user.terms_agreed_at = None
    user.privacy_policy_version = None
    user.terms_version = None
    user.profile_setup_completed = False
    user.feed_content_filter = "all"
    user.deleted_at = now


def _owned_agent_run_condition(user_id: str, character_ids: list[str]):
    return or_(
        models.AgentRun.user_id == user_id,
        _character_id_condition(models.AgentRun.character_id, character_ids),
    )


def _owned_agent_slot_condition(user_id: str, character_ids: list[str]):
    return or_(
        models.AgentSlot.assigned_user_id == user_id,
        _character_id_condition(models.AgentSlot.assigned_character_id, character_ids),
    )


def _character_id_condition(column, character_ids: list[str]):
    if not character_ids:
        return false()
    return column.in_(character_ids)


def _deleted_character_handle(db: Session, character_id: str) -> str:
    suffix = "".join(
        char.lower() for char in character_id if char.isalnum() or char in {"-", "_"}
    )
    suffix = suffix[-31:] or uuid4().hex[:12]
    base = f"deleted-{suffix}"[:40]
    candidate = base
    index = 2
    while db.scalar(
        select(models.Character.id).where(
            models.Character.handle == candidate,
            models.Character.id != character_id,
        )
    ):
        suffix_text = f"_{index}"
        candidate = f"{base[: 40 - len(suffix_text)]}{suffix_text}"
        index += 1
    return candidate


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
        payload = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
        )
    except (ValueError, GoogleAuthError) as exc:
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
