from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.core import security
from app.core.config import Settings
from app.domains.identity.application.migrate_local_credentials import (
    CredentialMigrationError,
    migrate_local_credential_envelope,
)
from app.domains.identity.application.resolve_credential import CredentialResolver
from scripts.migrate_local_credentials import migrate_local_credential_envelopes


@pytest.fixture
def scope() -> security.SecretScope:
    return security.SecretScope(
        owner_id="owner-1",
        character_id="character-1",
        provider="google",
        purpose="agent",
    )


def test_local_v2_round_trip_is_randomized_and_scoped(
    monkeypatch: pytest.MonkeyPatch,
    scope: security.SecretScope,
) -> None:
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)("l1-test-app-secret"),
    )
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "local")

    first = security.encrypt_secret("synthetic-api-key", scope=scope)
    second = security.encrypt_secret("synthetic-api-key", scope=scope)

    assert first.startswith("local-v2:")
    assert second.startswith("local-v2:")
    assert first != second
    assert security.decrypt_secret(first, scope=scope) == "synthetic-api-key"


def test_local_v2_rejects_tampering_and_wrong_scope(
    monkeypatch: pytest.MonkeyPatch,
    scope: security.SecretScope,
) -> None:
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)("l1-test-app-secret"),
    )
    payload = security.encrypt_local_secret("synthetic-api-key", scope=scope)
    wrong_scope = security.SecretScope(
        owner_id="owner-2",
        character_id=scope.character_id,
        provider=scope.provider,
        purpose=scope.purpose,
    )

    with pytest.raises(ValueError, match="scope does not match"):
        security.decrypt_secret(payload, scope=wrong_scope)

    replacement = "A" if payload[-1] != "A" else "B"
    with pytest.raises(ValueError, match="authentication"):
        security.decrypt_secret(payload[:-1] + replacement, scope=scope)


def test_dev_v1_is_readable_but_cannot_be_selected_for_new_writes(
    monkeypatch: pytest.MonkeyPatch,
    scope: security.SecretScope,
) -> None:
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)("l1-test-app-secret"),
    )
    legacy = security._encrypt_secret_legacy_local("synthetic-api-key")
    assert security.decrypt_secret(legacy) == "synthetic-api-key"

    monkeypatch.setattr(
        security.settings,
        "CREDENTIAL_ENCRYPTION_PROVIDER",
        "dev-v1",
    )
    with pytest.raises(ValueError, match="Unsupported credential encryption provider"):
        security.encrypt_secret("new-key", scope=scope)


def test_legacy_field_migrates_to_valid_local_v2(
    monkeypatch: pytest.MonkeyPatch,
    scope: security.SecretScope,
) -> None:
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)("l1-test-app-secret"),
    )
    result = migrate_local_credential_envelope(
        security._encrypt_secret_legacy_local("synthetic-api-key"),
        scope=scope,
        record_type="llm_credential",
        record_id="credential-1",
    )

    assert (result.migrated, result.current, result.external) == (1, 0, 0)
    assert result.envelope.startswith("local-v2:")
    assert (
        CredentialResolver.migrate_local_envelope(
            result.envelope,
            scope=scope,
        )
        == result.envelope
    )
    assert security.decrypt_secret(result.envelope, scope=scope) == "synthetic-api-key"


def test_invalid_legacy_field_requests_recovery_without_plaintext(
    scope: security.SecretScope,
) -> None:
    with pytest.raises(CredentialMigrationError) as caught:
        migrate_local_credential_envelope(
            "dev-v1:broken",
            scope=scope,
            record_type="llm_credential",
            record_id="credential-1",
        )

    assert caught.value.code == "credential_recovery_required"
    assert str(caught.value) == "credential_recovery_required"
    assert "broken" not in str(caught.value)


@pytest.fixture
def migration_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        models.User.__table__,
        models.Character.__table__,
        models.LlmCredential.__table__,
        models.AgentCreationDraft.__table__,
        models.AgentImageGenerationSetting.__table__,
    ):
        table.create(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def _legacy(value: str) -> str:
    return security._encrypt_secret_legacy_local(value)


def test_migration_atomically_converts_every_local_credential_type(
    monkeypatch: pytest.MonkeyPatch,
    migration_db: Session,
) -> None:
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)("l1-atomic-test-secret"),
    )
    owner = models.User(id="owner-1", display_name="Owner")
    character = models.Character(
        id="character-1",
        owner_id=owner.id,
        name="Mango",
        handle="mango-l1-test",
        persona_summary="",
    )
    credential = models.LlmCredential(
        id="credential-1",
        owner_id=owner.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-3.1-flash-lite",
        auth_profile_id="profile-1",
        label="test",
        encrypted_api_key=_legacy("llm-key"),
        enabled=True,
    )
    draft = models.AgentCreationDraft(
        id="draft-1",
        user_id=owner.id,
        provider="google",
        model="gemini-3.1-flash-lite",
        encrypted_api_key=_legacy("draft-key"),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    image = models.AgentImageGenerationSetting(
        character_id=character.id,
        encrypted_pollinations_api_key=_legacy("image-key"),
    )
    migration_db.add_all([owner, character, credential, draft, image])
    migration_db.commit()

    result = migrate_local_credential_envelopes(migration_db)

    assert result.inspected == 3
    assert result.migrated == 3
    assert result.current == 0
    assert result.external == 0
    assert security.decrypt_secret(
        credential.encrypted_api_key,
        scope=security.SecretScope(
            owner_id=owner.id,
            character_id=character.id,
            provider="google",
            purpose="agent",
        ),
    ) == "llm-key"
    assert security.decrypt_secret(
        draft.encrypted_api_key,
        scope=security.SecretScope(
            owner_id=owner.id,
            character_id="",
            provider="google",
            purpose="creation_draft",
        ),
    ) == "draft-key"
    assert security.decrypt_secret(
        image.encrypted_pollinations_api_key,
        scope=security.SecretScope(
            owner_id=owner.id,
            character_id=character.id,
            provider="pollinations",
            purpose="user_image",
        ),
    ) == "image-key"


def test_migration_rolls_back_all_rows_when_one_envelope_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    migration_db: Session,
) -> None:
    monkeypatch.setattr(
        security.settings,
        "APP_SECRET",
        type(security.settings.APP_SECRET)("l1-rollback-test-secret"),
    )
    owner = models.User(id="owner-rollback", display_name="Rollback Owner")
    good = models.LlmCredential(
        id="a-good",
        owner_id=owner.id,
        character_id=None,
        provider="google",
        purpose="message",
        model="gemini-3.1-flash-lite",
        auth_profile_id="profile-good",
        label="good",
        encrypted_api_key=_legacy("good-key"),
        enabled=True,
    )
    bad = models.LlmCredential(
        id="z-bad",
        owner_id=owner.id,
        character_id=None,
        provider="google",
        purpose="message",
        model="gemini-3.1-flash-lite",
        auth_profile_id="profile-bad",
        label="bad",
        encrypted_api_key="dev-v1:broken",
        enabled=True,
    )
    migration_db.add_all([owner, good, bad])
    migration_db.commit()
    original_good = good.encrypted_api_key

    with pytest.raises(CredentialMigrationError) as caught:
        migrate_local_credential_envelopes(migration_db)

    assert caught.value.record_id == "z-bad"
    migration_db.expire_all()
    stored_good = migration_db.scalar(
        select(models.LlmCredential).where(models.LlmCredential.id == "a-good")
    )
    assert stored_good is not None
    assert stored_good.encrypted_api_key == original_good
    assert stored_good.encrypted_api_key.startswith("dev-v1:")


def test_settings_reads_app_secret_from_file_without_environment_value(
    tmp_path,
) -> None:
    secret_file = tmp_path / "app_secret"
    secret_file.write_text("synthetic-file-secret\n", encoding="utf-8")
    config = Settings(
        APP_SECRET_FILE=str(secret_file),
        APP_SECRET=type(security.settings.APP_SECRET)("unused-fallback"),
        _env_file=None,
    )

    assert config.app_secret == "synthetic-file-secret"


def test_settings_rejects_a_missing_app_secret_file(tmp_path) -> None:
    config = Settings(
        APP_SECRET_FILE=str(tmp_path / "missing"),
        APP_SECRET=type(security.settings.APP_SECRET)("unused-fallback"),
        _env_file=None,
    )

    with pytest.raises(ValueError, match="app_secret_file_invalid"):
        _ = config.app_secret
