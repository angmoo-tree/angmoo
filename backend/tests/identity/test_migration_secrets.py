"""Explicit local migration keys do not inherit globals or contact a provider."""
from pydantic import SecretStr
import pytest

from app.core import security
from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter


@pytest.mark.parametrize("legacy", [False, True])
def test_local_migration_authentication_uses_only_the_injected_key(
    monkeypatch, tmp_path, legacy, deny_external_network,
):
    scope = security.SecretScope(owner_id="synthetic-owner", character_id="synthetic-character",
                                 provider="google", purpose="agent")
    app_secret = "synthetic-migration-app-secret"
    with monkeypatch.context() as original_settings:
        original_settings.setattr(security.settings, "APP_SECRET_FILE", None)
        original_settings.setattr(security.settings, "APP_SECRET", SecretStr(app_secret))
        envelope = (security._encrypt_secret_legacy_local("synthetic-key") if legacy else
                    security.encrypt_local_secret("synthetic-key", scope=scope))
    monkeypatch.setattr(security.settings, "APP_SECRET_FILE", str(tmp_path / "missing-process-secret"))
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "oci_kms")
    original = security.settings.model_dump()
    interpreter = MigrationSecretInterpreter(secret_source=lambda: app_secret)
    assert interpreter(envelope, scope.as_dict()) is None
    assert security.decrypt_local_secret(envelope, scope=scope, app_secret=app_secret) == "synthetic-key"
    with pytest.raises(ValueError, match="authentication"):
        MigrationSecretInterpreter(secret_source=lambda: "incorrect-secret")(envelope, scope.as_dict())
    assert security.settings.model_dump() == original


def test_local_migration_keeps_scope_authentication_and_rejects_remote_envelopes(deny_external_network):
    scope = security.SecretScope(owner_id="synthetic-owner", character_id="synthetic-character",
                                 provider="google", purpose="agent")
    envelope = security.encrypt_local_secret("synthetic-key", scope=scope, app_secret="explicit-secret")
    interpreter = MigrationSecretInterpreter(secret_source=lambda: "explicit-secret")
    with pytest.raises(ValueError, match="scope does not match"):
        interpreter(envelope, {**scope.as_dict(), "owner_id": "other-owner"})
    with pytest.raises(ValueError, match="Unsupported local credential envelope"):
        interpreter("oci-kms-v1:synthetic:synthetic", scope.as_dict())


def test_empty_migration_secret_never_falls_back_to_process_settings():
    with pytest.raises(ValueError, match="migration_app_secret_empty"):
        MigrationSecretInterpreter(secret_source=lambda: " ")("synthetic-envelope", {})


def test_owned_secret_is_read_only_when_needed_and_once_per_transition():
    reads = []
    value = ["original-owned-secret"]

    def source():
        reads.append(True)
        return value[0]

    scope = security.SecretScope(owner_id="synthetic-owner", character_id="synthetic-character",
                                 provider="google", purpose="agent")
    envelope = security.encrypt_local_secret("synthetic-key", scope=scope, app_secret=value[0])
    interpreter = MigrationSecretInterpreter(secret_source=source)
    assert reads == []
    interpreter(envelope, scope.as_dict())
    value[0] = "changed-source-secret"
    interpreter(envelope, scope.as_dict())
    assert len(reads) == 1
