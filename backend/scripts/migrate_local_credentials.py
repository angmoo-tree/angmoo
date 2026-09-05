from __future__ import annotations

from dataclasses import dataclass
import sys

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.core import security
from app.core.config import settings
from app.core.db import SessionLocal
from app.domains.identity.exceptions import CredentialMigrationError
from app.domains.identity.service.credential_migration import migrate_local_credential_envelope


_MIGRATION_ADVISORY_LOCK = 4_721_001_002


@dataclass(frozen=True)
class CredentialMigrationResult:
    inspected: int = 0
    migrated: int = 0
    current: int = 0
    external: int = 0


def migrate_local_credential_envelopes(db: Session) -> CredentialMigrationResult:
    """Atomically validate local-v2 envelopes and migrate every dev-v1 row."""

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _MIGRATION_ADVISORY_LOCK},
        )

    inspected = 0
    migrated = 0
    current = 0
    external = 0
    try:
        for credential in db.scalars(
            select(models.LlmCredential).order_by(models.LlmCredential.id)
        ):
            if not credential.encrypted_api_key:
                continue
            inspected += 1
            outcome = migrate_local_credential_envelope(
                credential.encrypted_api_key,
                scope=security.SecretScope(
                    owner_id=credential.owner_id,
                    character_id=credential.character_id or "",
                    provider=credential.provider,
                    purpose=credential.purpose,
                ),
                record_type="llm_credential",
                record_id=credential.id,
            )
            credential.encrypted_api_key = outcome.envelope
            migrated += outcome.migrated
            current += outcome.current
            external += outcome.external

        for draft in db.scalars(
            select(models.AgentCreationDraft).order_by(models.AgentCreationDraft.id)
        ):
            if not draft.encrypted_api_key:
                continue
            inspected += 1
            outcome = migrate_local_credential_envelope(
                draft.encrypted_api_key,
                scope=security.SecretScope(
                    owner_id=draft.user_id,
                    character_id="",
                    provider=draft.provider,
                    purpose="creation_draft",
                ),
                record_type="agent_creation_draft",
                record_id=draft.id,
            )
            draft.encrypted_api_key = outcome.envelope
            migrated += outcome.migrated
            current += outcome.current
            external += outcome.external

        image_rows = db.execute(
            select(models.AgentImageGenerationSetting, models.Character.owner_id)
            .join(
                models.Character,
                models.Character.id
                == models.AgentImageGenerationSetting.character_id,
            )
        ).all()
        for setting, owner_id in image_rows:
            for field_name, provider in (
                ("encrypted_openrouter_api_key", "openrouter"),
                ("encrypted_pollinations_api_key", "pollinations"),
                ("encrypted_replicate_api_token", "replicate"),
            ):
                envelope = getattr(setting, field_name)
                if not envelope:
                    continue
                inspected += 1
                outcome = migrate_local_credential_envelope(
                    envelope,
                    scope=security.SecretScope(
                        owner_id=owner_id,
                        character_id=setting.character_id,
                        provider=provider,
                        purpose="user_image",
                    ),
                    record_type="agent_image_generation_setting",
                    record_id=f"{setting.character_id}:{provider}",
                )
                setattr(setting, field_name, outcome.envelope)
                migrated += outcome.migrated
                current += outcome.current
                external += outcome.external

        db.commit()
    except Exception:
        db.rollback()
        raise
    return CredentialMigrationResult(
        inspected=inspected,
        migrated=migrated,
        current=current,
        external=external,
    )


def main() -> int:
    if settings.credential_encryption_provider not in {"local", "dev", "local-v2"}:
        print("credential_migration_skipped provider=external")
        return 0
    with SessionLocal() as db:
        try:
            result = migrate_local_credential_envelopes(db)
        except CredentialMigrationError as exc:
            print(
                "credential_recovery_required "
                f"record_type={exc.record_type} record_id={exc.record_id}",
                file=sys.stderr,
            )
            return 78
    print(
        "credential_migration_complete "
        f"inspected={result.inspected} migrated={result.migrated} "
        f"current={result.current} external={result.external}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
