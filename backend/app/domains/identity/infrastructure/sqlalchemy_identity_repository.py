from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.domains.identity.domain.local_owner import (
    LOCAL_INSTALLATION_KEY,
    BootstrapChallengeInvalidError,
    BootstrapClosedError,
    BootstrapRaceLostError,
    IssuedBootstrapChallenge,
    IssuedLocalSession,
    LocalBootstrapStatus,
    LocalOwnerCandidate,
    LocalOwnerCandidateInvalidError,
    LocalOwnerPrivacyAcknowledgementRequiredError,
    LocalOwnerProfileInvalidError,
    LocalOwnerUnclaimedError,
    LocalSessionRateLimitedError,
    LocalSessionUnavailableError,
    LocalUserSnapshot,
    normalize_local_display_name,
    normalize_local_label,
)
from app.domains.identity.infrastructure.sqlalchemy_auth_models import (
    AuthSession,
    InstallationIdentity,
    LocalOwnerBootstrapChallenge,
    User,
)


BOOTSTRAP_CHALLENGE_TTL = timedelta(minutes=10)
LOCAL_SESSION_TTL = timedelta(days=7)
LOCAL_SESSION_RATE_WINDOW = timedelta(minutes=1)
LOCAL_SESSION_RATE_LIMIT = 10


class SqlAlchemyIdentityRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_bootstrap_status(self) -> LocalBootstrapStatus:
        identity = self._db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
        if identity is not None and identity.bootstrap_state == "recovery_required":
            return LocalBootstrapStatus(
                state="recovery_required",
                installation_id=identity.installation_id,
                local_label=identity.local_label,
                owner=None,
                candidates=(),
            )
        if identity is not None and identity.owner_user_id is not None:
            owner = self._db.get(User, identity.owner_user_id)
            if owner is None or owner.deleted_at is not None:
                return LocalBootstrapStatus(
                    state="recovery_required",
                    installation_id=identity.installation_id,
                    local_label=identity.local_label,
                    owner=None,
                    candidates=(),
                )
            return LocalBootstrapStatus(
                state=identity.bootstrap_state,
                installation_id=identity.installation_id,
                local_label=identity.local_label,
                owner=_snapshot(owner),
                candidates=(),
            )

        return LocalBootstrapStatus(
            state="unclaimed",
            installation_id=identity.installation_id if identity else None,
            local_label=identity.local_label if identity else None,
            owner=None,
            candidates=self._owner_candidates(),
        )

    def create_bootstrap_challenge(
        self,
        *,
        now: datetime,
    ) -> IssuedBootstrapChallenge:
        identity = self._get_or_create_identity(now)
        if identity.owner_user_id is not None or identity.bootstrap_state != "unclaimed":
            self._db.rollback()
            raise BootstrapClosedError("local owner is already claimed")

        normalized_now = _as_utc(now)
        self._db.execute(
            update(LocalOwnerBootstrapChallenge)
            .where(
                LocalOwnerBootstrapChallenge.installation_key
                == LOCAL_INSTALLATION_KEY,
                LocalOwnerBootstrapChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=normalized_now)
        )
        token = secrets.token_urlsafe(32)
        expires_at = normalized_now + BOOTSTRAP_CHALLENGE_TTL
        self._db.add(
            LocalOwnerBootstrapChallenge(
                challenge_hash=_hash_challenge(token),
                installation_key=LOCAL_INSTALLATION_KEY,
                expires_at=expires_at,
                created_at=normalized_now,
            )
        )
        self._db.commit()
        return IssuedBootstrapChallenge(token=token, expires_at=expires_at)

    def claim_local_owner(
        self,
        *,
        challenge_token: str,
        owner_user_id: str | None,
        display_name: str | None,
        local_label: str | None,
        privacy_acknowledged: bool,
        now: datetime,
    ) -> IssuedLocalSession:
        normalized_now = _as_utc(now)
        identity = self._db.scalar(
            select(InstallationIdentity)
            .where(InstallationIdentity.singleton_key == LOCAL_INSTALLATION_KEY)
            .with_for_update()
        )
        if identity is None:
            self._db.rollback()
            raise BootstrapChallengeInvalidError("installation identity is missing")
        if identity.owner_user_id is not None or identity.bootstrap_state != "unclaimed":
            self._db.rollback()
            raise BootstrapRaceLostError("another local owner claim already succeeded")

        challenge = self._db.scalar(
            select(LocalOwnerBootstrapChallenge)
            .where(
                LocalOwnerBootstrapChallenge.challenge_hash
                == _hash_challenge(challenge_token)
            )
            .with_for_update()
        )
        if (
            challenge is None
            or challenge.installation_key != LOCAL_INSTALLATION_KEY
            or challenge.consumed_at is not None
            or _as_utc(challenge.expires_at) <= normalized_now
            or challenge.attempt_count >= 5
        ):
            self._db.rollback()
            raise BootstrapChallengeInvalidError("invalid or expired bootstrap challenge")

        challenge.attempt_count += 1
        try:
            if not privacy_acknowledged:
                raise LocalOwnerPrivacyAcknowledgementRequiredError(
                    "local data ownership must be acknowledged"
                )
            normalized_local_label = normalize_local_label(local_label)
            user = self._select_or_create_owner(
                owner_user_id=owner_user_id,
                display_name=display_name,
            )
        except (
            LocalOwnerCandidateInvalidError,
            LocalOwnerPrivacyAcknowledgementRequiredError,
            LocalOwnerProfileInvalidError,
        ):
            self._db.commit()
            raise
        identity.owner_user_id = user.id
        identity.bootstrap_state = "claimed"
        identity.local_label = normalized_local_label
        identity.claimed_at = normalized_now
        identity.updated_at = normalized_now
        challenge.consumed_at = normalized_now
        self._db.execute(
            update(LocalOwnerBootstrapChallenge)
            .where(
                LocalOwnerBootstrapChallenge.installation_key
                == LOCAL_INSTALLATION_KEY,
                LocalOwnerBootstrapChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=normalized_now)
        )
        issued = self._add_local_session(user, normalized_now)
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise BootstrapRaceLostError("another local owner claim won") from exc
        return issued

    def issue_local_session(
        self,
        *,
        now: datetime,
        secret_ready: bool,
    ) -> IssuedLocalSession:
        if not secret_ready:
            raise LocalSessionUnavailableError("APP_SECRET is not ready")
        normalized_now = _as_utc(now)
        identity = self._db.scalar(
            select(InstallationIdentity)
            .where(InstallationIdentity.singleton_key == LOCAL_INSTALLATION_KEY)
            .with_for_update()
        )
        if identity is None or identity.owner_user_id is None:
            self._db.rollback()
            raise LocalOwnerUnclaimedError("local owner is not claimed")
        owner = self._db.get(User, identity.owner_user_id)
        if owner is None or owner.deleted_at is not None:
            self._db.rollback()
            raise LocalSessionUnavailableError("local owner principal is unavailable")
        recent_count = self._db.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == owner.id,
                AuthSession.auth_method == "local_owner",
                AuthSession.created_at >= normalized_now - LOCAL_SESSION_RATE_WINDOW,
            )
        )
        if int(recent_count or 0) >= LOCAL_SESSION_RATE_LIMIT:
            self._db.rollback()
            raise LocalSessionRateLimitedError("local session issuance rate limited")
        issued = self._add_local_session(owner, normalized_now)
        self._db.commit()
        return issued

    def _get_or_create_identity(self, now: datetime) -> InstallationIdentity:
        identity = self._db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
        if identity is not None:
            return identity
        normalized_now = _as_utc(now)
        identity = InstallationIdentity(
            singleton_key=LOCAL_INSTALLATION_KEY,
            installation_id=str(uuid4()),
            bootstrap_state="unclaimed",
            created_at=normalized_now,
            updated_at=normalized_now,
        )
        self._db.add(identity)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            identity = self._db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
            if identity is None:
                raise
        return identity

    def _select_or_create_owner(
        self,
        *,
        owner_user_id: str | None,
        display_name: str | None,
    ) -> User:
        if owner_user_id:
            user = self._db.get(User, owner_user_id)
            if user is None or user.deleted_at is not None:
                raise LocalOwnerCandidateInvalidError("invalid local owner candidate")
            return user

        normalized_display_name, normalized_key = normalize_local_display_name(
            display_name
        )
        duplicate = self._db.scalar(
            select(User.id).where(User.display_name_normalized == normalized_key)
        )
        if duplicate is not None:
            raise LocalOwnerCandidateInvalidError("local owner display name already exists")
        user = User(
            id=f"user-local-{uuid4().hex}",
            email=None,
            google_sub=None,
            password_hash=None,
            display_name=normalized_display_name,
            display_name_normalized=normalized_key,
            profile_setup_completed=True,
            feed_content_filter="all",
            is_admin=False,
        )
        self._db.add(user)
        self._db.flush()
        return user

    def _add_local_session(
        self,
        user: User,
        now: datetime,
    ) -> IssuedLocalSession:
        token = security.create_token()
        expires_at = now + LOCAL_SESSION_TTL
        self._db.add(
            AuthSession(
                token_hash=security.hash_token(token),
                user_id=user.id,
                auth_method="local_owner",
                created_at=now,
                expires_at=expires_at,
            )
        )
        return IssuedLocalSession(
            token=token,
            expires_at=expires_at,
            user=_snapshot(user),
        )

    def _owner_candidates(self) -> tuple[LocalOwnerCandidate, ...]:
        users = tuple(
            self._db.scalars(
                select(User)
                .where(User.deleted_at.is_(None))
                .order_by(User.created_at.asc(), User.id.asc())
            )
        )
        return tuple(
            LocalOwnerCandidate(
                user_id=user.id,
                display_name=user.display_name,
                character_count=self._count(
                    "SELECT count(*) FROM characters "
                    "WHERE owner_id = :owner_id AND deleted_at IS NULL",
                    user.id,
                ),
                world_count=self._count(
                    "SELECT count(*) FROM world_memberships "
                    "WHERE user_id = :owner_id AND status = 'active'",
                    user.id,
                ),
                credential_count=self._count(
                    "SELECT count(*) FROM llm_credentials WHERE owner_id = :owner_id",
                    user.id,
                ),
            )
            for user in users
        )

    def _count(self, statement: str, owner_id: str) -> int:
        return int(self._db.scalar(text(statement), {"owner_id": owner_id}) or 0)


def _hash_challenge(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _snapshot(user: User) -> LocalUserSnapshot:
    return LocalUserSnapshot(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        profile_setup_completed=user.profile_setup_completed,
        feed_content_filter=user.feed_content_filter,
        is_admin=user.is_admin,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
