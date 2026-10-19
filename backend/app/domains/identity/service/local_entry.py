"""Atomic local bootstrap and client-scoped stop/resume transitions.

Only protected Local HTTP entry points call these methods. Client identifiers
coordinate intent; the normal token/expiry/client-generation check authenticates.
"""
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import AuthSession, InstallationIdentity, LocalClientConnection, LocalOwnerBootstrapChallenge, User
from app.domains.identity.policies import normalize_local_label
from app.domains.identity.schemas_local_entry import LocalClientRead, LocalClientRequest, LocalPrepareRequest
from app.domains.identity.service.local_owner import (
    LOCAL_SESSION_RATE_LIMIT, LOCAL_SESSION_RATE_WINDOW, LOCAL_SESSION_TTL, LocalIdentityService, _as_utc,
    _hash_challenge, utcnow,
)
from app.models import Base


class LocalEntryError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


def has_existing_owner_data(db: Session) -> bool:
    # All user rows, including deleted users, block a fresh bootstrap. Foreign
    # key owners also catch orphaned data from older imports with FK disabled.
    for table in Base.metadata.tables.values():
        if table.name == "users" or any(fk.target_fullname == "users.id" for fk in table.foreign_keys):
            if table.name == "installation_identities":
                continue
            if db.scalar(select(func.count()).select_from(select(table).limit(1).subquery())):
                return True
    return False


class LocalEntryService:
    def __init__(self, db: Session, *, clock=utcnow):
        self.db, self.clock = db, clock

    def _write(self, operation):
        # This service owns the complete UoW. Callers must close dependency
        # reads explicitly; never discard another caller's flushed writes.
        if self.db.in_transaction():
            raise RuntimeError("local_entry_requires_clean_session")
        if self.db.get_bind().dialect.name == "sqlite":
            return run_sqlite_session_immediate(self.db, operation, require_clean=True)
        with self.db.begin():
            return operation()

    def _identity(self, installation_id: str, *, lock: bool = True):
        query = select(InstallationIdentity).where(InstallationIdentity.singleton_key == LOCAL_INSTALLATION_KEY)
        identity = self.db.scalar(query.with_for_update() if lock else query)
        if identity is None or identity.installation_id != installation_id:
            raise LocalEntryError("local_auth_contract_mismatch")
        if identity.bootstrap_state == "recovery_required":
            raise LocalEntryError("local_identity_recovery_required")
        return identity

    def _client(self, data: LocalClientRequest, *, create: bool):
        key = sha256(f"{data.installation_id}:{data.client_instance_id}".encode()).hexdigest()
        client = self.db.get(LocalClientConnection, key)
        if client is None and create:
            if data.expected_generation != 0:
                raise LocalEntryError("local_client_revision_conflict")
            client = LocalClientConnection(id=key, installation_id=data.installation_id,
                client_instance_id=data.client_instance_id, generation=0, state="active",
                created_at=self.clock(), updated_at=self.clock())
            self.db.add(client)
            self.db.flush()
        return client

    @staticmethod
    def _read(client, data):
        return LocalClientRead(installation_id=data.installation_id, client_instance_id=data.client_instance_id,
            generation=client.generation if client else 0, state=client.state if client else "active")

    def status(self, data: LocalClientRequest):
        self._identity(data.installation_id, lock=False)
        return self._read(self._client(data, create=False), data)

    def update_label(self, *, installation_id: str, owner_id: str, label: str | None):
        normalized = normalize_local_label(label)
        def operation():
            identity = self._identity(installation_id)
            if identity.bootstrap_state != "claimed" or identity.owner_user_id != owner_id:
                raise LocalEntryError("local_owner_required", 403)
            identity.local_label = normalized
            identity.updated_at = self.clock()
            return {"local_label": normalized}
        return self._write(operation)

    def _active(self, client, data):
        if client.state != "active":
            raise LocalEntryError("local_client_stopped")
        if client.generation != data.expected_generation:
            raise LocalEntryError("local_client_revision_conflict")

    def _owner(self, identity):
        if identity.owner_user_id is None:
            raise LocalEntryError("local_owner_unclaimed")
        owner = self.db.get(User, identity.owner_user_id)
        if owner is None or owner.deleted_at is not None:
            raise LocalEntryError("local_identity_recovery_required")
        return owner

    def _issue(self, owner, client, now):
        count = self.db.scalar(select(func.count()).select_from(AuthSession).where(
            AuthSession.user_id == owner.id, AuthSession.auth_method == "local_owner",
            AuthSession.created_at >= now - LOCAL_SESSION_RATE_WINDOW))
        if int(count or 0) >= LOCAL_SESSION_RATE_LIMIT:
            raise LocalEntryError("local_session_rate_limited", 429)
        issued = LocalIdentityService(self.db)._add_local_session(owner, now)
        self.db.flush()
        session = self.db.get(AuthSession, security.hash_token(issued.token))
        session.local_client_id, session.local_client_generation = client.id, client.generation
        return issued

    def prepare(self, data: LocalPrepareRequest, *, challenge_token: str, secret_ready: bool,
                owner_user_id: str | None = None, local_label: str | None = None):
        if not secret_ready:
            raise LocalEntryError("local_session_unavailable", 503)
        now = _as_utc(self.clock())
        def operation():
            identity = self._identity(data.installation_id)
            client = self._client(data, create=True)
            self._active(client, data)
            # A competing prepare has already committed: continue as that owner.
            if identity.owner_user_id is not None:
                return self._issue(self._owner(identity), client, now)
            challenge = self.db.get(LocalOwnerBootstrapChallenge, _hash_challenge(challenge_token))
            if (challenge is None or challenge.consumed_at is not None or challenge.attempt_count >= 5
                    or _as_utc(challenge.expires_at) <= now or challenge.installation_key != LOCAL_INSTALLATION_KEY):
                raise LocalEntryError("bootstrap_challenge_invalid", 401)
            challenge.attempt_count += 1
            if owner_user_id is None:
                if has_existing_owner_data(self.db):
                    return LocalEntryError("legacy_owner_selection_required")
                name = "사용자" if (data.preferred_language or "en").split("-")[0].lower() == "ko" else "User"
                owner = LocalIdentityService(self.db)._select_or_create_owner(owner_user_id=None, display_name=name)
            else:
                owner = self.db.get(User, owner_user_id)
                if owner is None or owner.deleted_at is not None:
                    return LocalEntryError("local_owner_candidate_invalid", 422)
            identity.owner_user_id, identity.bootstrap_state = owner.id, "claimed"
            identity.local_label = normalize_local_label(local_label)
            identity.claimed_at = identity.updated_at = now
            challenge.consumed_at = now
            return self._issue(owner, client, now)
        result = self._write(operation)
        if isinstance(result, LocalEntryError):
            raise result
        return result

    def issue(self, data: LocalClientRequest, *, secret_ready: bool, current_token: str | None = None):
        if not secret_ready:
            raise LocalEntryError("local_session_unavailable", 503)
        now = _as_utc(self.clock())
        def operation():
            identity = self._identity(data.installation_id)
            client = self._client(data, create=True)
            self._active(client, data)
            owner = self._owner(identity)
            # Adopt a valid legacy session once without replacing its token/TTL.
            if current_token:
                from app.domains.identity.service.auth import get_session_for_token
                session = get_session_for_token(self.db, current_token)
                if session and session.user_id == owner.id and session.auth_method == "local_owner":
                    if session.local_client_id not in (None, client.id):
                        raise LocalEntryError("local_client_session_mismatch")
                    session.local_client_id, session.local_client_generation = client.id, client.generation
                    from app.domains.identity.contracts import IssuedLocalSession
                    from app.domains.identity.service.local_owner import _snapshot
                    return IssuedLocalSession(token=current_token, expires_at=session.expires_at or _as_utc(session.created_at) + LOCAL_SESSION_TTL,
                                              user=_snapshot(owner))
            return self._issue(owner, client, now)
        return self._write(operation)

    def stop(self, data: LocalClientRequest, *, current_token: str | None = None):
        def operation():
            self._identity(data.installation_id)
            client = self._client(data, create=True)
            if client.state == "stopped" and client.generation in (data.expected_generation, data.expected_generation + 1):
                return self._read(client, data)
            if client.generation != data.expected_generation:
                raise LocalEntryError("local_client_revision_conflict")
            client.state, client.generation, client.updated_at = "stopped", client.generation + 1, self.clock()
            if current_token:
                session = self.db.get(AuthSession, security.hash_token(current_token))
                if session and session.local_client_id == client.id:
                    self.db.delete(session)
            return self._read(client, data)
        return self._write(operation)

    def resume(self, data: LocalClientRequest, *, secret_ready: bool):
        if not secret_ready:
            raise LocalEntryError("local_session_unavailable", 503)
        now = _as_utc(self.clock())
        def operation():
            identity = self._identity(data.installation_id)
            client = self._client(data, create=False)
            if client is None or client.state != "stopped" or client.generation != data.expected_generation:
                raise LocalEntryError("local_client_revision_conflict")
            client.state, client.generation, client.updated_at = "active", client.generation + 1, now
            if identity.owner_user_id is None:
                return self._read(client, data)
            return self._issue(self._owner(identity), client, now)
        return self._write(operation)
