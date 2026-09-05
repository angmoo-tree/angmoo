from __future__ import annotations

from dataclasses import dataclass

from app.core import security
from app.domains.identity.service.credential_resolution import CredentialResolver


from app.domains.identity.exceptions import CredentialMigrationError


@dataclass(frozen=True)
class CredentialEnvelopeMigration:
    envelope: str
    migrated: int = 0
    current: int = 0
    external: int = 0


def migrate_local_credential_envelope(
    envelope: str,
    *,
    scope: security.SecretScope,
    record_type: str,
    record_id: str,
) -> CredentialEnvelopeMigration:
    """Validate one envelope and return its local-v2 replacement when needed.

    Persistence and transaction ownership intentionally stay outside the application
    layer so this domain service does not depend on SQLAlchemy or legacy ORM models.
    """

    try:
        if envelope.startswith(f"{security.LOCAL_SECRET_PREFIX}:"):
            CredentialResolver.migrate_local_envelope(envelope, scope=scope)
            return CredentialEnvelopeMigration(envelope=envelope, current=1)
        if envelope.startswith(f"{security.LEGACY_LOCAL_SECRET_PREFIX}:"):
            migrated = CredentialResolver.migrate_local_envelope(
                envelope,
                scope=scope,
            )
            return CredentialEnvelopeMigration(envelope=migrated, migrated=1)
        if envelope.startswith(f"{security.OCI_KMS_SECRET_PREFIX}:"):
            return CredentialEnvelopeMigration(envelope=envelope, external=1)
        raise ValueError("unsupported credential envelope")
    except ValueError as exc:
        raise CredentialMigrationError(
            "credential_recovery_required",
            record_type=record_type,
            record_id=record_id,
        ) from exc
