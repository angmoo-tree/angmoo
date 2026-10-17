"""Retiring hosted KMS preserves local keys and never sends ciphertext as a key."""
from __future__ import annotations

import builtins
from contextlib import nullcontext
import json
from pathlib import Path

from pydantic import SecretStr
import pytest

from app.config import Settings
from app.core import security
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.service.credential_migration import migrate_local_credential_envelope
from app.domains.identity.service.credential_resolution import CredentialResolver
from scripts import migrate_local_credentials as migration_cli


@pytest.fixture
def previous_local_keys(monkeypatch):
    # Generated using main caf75878 before removing KMS; all values are synthetic.
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/pre_kms_retirement_envelopes.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(security.settings, "APP_SECRET_FILE", None)
    monkeypatch.setattr(security.settings, "APP_SECRET", SecretStr(fixture["app_secret"]))
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "local")
    return fixture, security.SecretScope(**fixture["scope"])


@pytest.fixture
def forbid_oracle_import(monkeypatch, deny_external_network):
    original = builtins.__import__
    attempts = []

    def guarded(name, *args, **kwargs):
        if name == "oci" or name.startswith("oci."):
            attempts.append(name)
            raise AssertionError("Retired SDK must not be loaded")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    yield
    assert attempts == []


@pytest.mark.parametrize("version", ["local_v2", "dev_v1"])
def test_pre_retirement_local_keys_still_decrypt_and_migrate(previous_local_keys, version):
    fixture, scope = previous_local_keys
    envelope = fixture[version]
    assert security.decrypt_secret(envelope, scope=scope) == fixture["plaintext"]
    assert security.decrypt_local_secret(
        envelope, scope=scope, app_secret=fixture["app_secret"],
    ) == fixture["plaintext"]
    migrated = CredentialResolver.migrate_local_envelope(envelope, scope=scope)
    assert security.decrypt_secret(migrated, scope=scope) == fixture["plaintext"]
    assert CredentialResolver.migrate_local_envelope(migrated, scope=scope) == migrated
    if version == "local_v2":
        assert migrated == envelope


@pytest.mark.parametrize("field", ["owner_id", "character_id", "provider", "purpose"])
def test_pre_retirement_local_key_rejects_each_wrong_scope(previous_local_keys, field):
    fixture, scope = previous_local_keys
    wrong = security.SecretScope(**{**scope.as_dict(), field: "different-value"})
    with pytest.raises(ValueError, match="scope does not match"):
        security.decrypt_local_secret(fixture["local_v2"], scope=wrong, app_secret=fixture["app_secret"])


@pytest.mark.parametrize("version", ["local_v2", "dev_v1"])
def test_pre_retirement_local_key_rejects_another_root_key(previous_local_keys, version):
    fixture, scope = previous_local_keys
    with pytest.raises(ValueError, match="authentication"):
        security.decrypt_local_secret(fixture[version], scope=scope, app_secret="another-synthetic-root")


@pytest.mark.parametrize("provider", ["local", "dev", "local-v2", " LOCAL "])
def test_local_provider_aliases_keep_authenticated_current_envelopes(
    previous_local_keys, monkeypatch, provider, forbid_oracle_import,
):
    fixture, scope = previous_local_keys
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", provider)
    envelope = security.encrypt_secret(fixture["plaintext"], scope=scope)
    assert envelope.startswith("local-v2:")
    assert security.decrypt_secret(envelope, scope=scope) == fixture["plaintext"]


@pytest.mark.parametrize("provider", ["oci_kms", "oci-kms", "dev-v1", "synthetic-private-value"])
def test_retired_provider_never_encrypts_or_leaks_configuration(
    previous_local_keys, monkeypatch, provider, forbid_oracle_import,
):
    _, scope = previous_local_keys
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", provider)
    with pytest.raises(ValueError) as caught:
        security.encrypt_secret("synthetic-plaintext", scope=scope)
    assert str(caught.value) == "Unsupported credential encryption provider"


@pytest.mark.parametrize("envelope", [
    "oci-kms-v1:",
    "oci-kms-v1:malformed",
    "oci-kms-v1:synthetic-key-id:synthetic-ciphertext",
])
def test_retired_envelope_cannot_be_resolved_as_a_configured_plaintext_key(
    envelope, forbid_oracle_import,
):
    with pytest.raises(CredentialResolutionError) as caught:
        CredentialResolver.resolve_configured_secret(
            envelope, credential_id="synthetic-service-key", provider="pollinations",
            model="synthetic-model", purpose=CredentialPurpose.SERVICE_IMAGE,
        )
    assert str(caught.value) == "credential key cannot be decrypted"
    assert str(caught.value.__cause__) == "Unsupported credential envelope"
    with pytest.raises(ValueError, match="Unsupported credential envelope"):
        security.decrypt_secret(envelope)


@pytest.mark.parametrize("encrypted", [False, True])
def test_configured_current_keys_remain_available(previous_local_keys, encrypted, forbid_oracle_import):
    fixture, _ = previous_local_keys
    value = fixture["local_v2"] if encrypted else fixture["plaintext"]
    material = CredentialResolver.resolve_configured_secret(
        value, credential_id="synthetic-service-key", provider="google",
        model="synthetic-model", purpose=CredentialPurpose.SERVICE_IMAGE,
    )
    assert material is not None
    assert material.reveal() == fixture["plaintext"]
    assert fixture["plaintext"] not in repr(material)
    assert value not in repr(material)


@pytest.mark.parametrize("record_type", ["llm_credential", "agent_creation_draft", "agent_image_generation_setting"])
def test_retired_envelope_is_preserved_as_external_not_validated_local(
    previous_local_keys, record_type, forbid_oracle_import,
):
    _, scope = previous_local_keys
    original = "oci-kms-v1:synthetic-key-id:synthetic-ciphertext"
    result = migrate_local_credential_envelope(
        original, scope=scope, record_type=record_type, record_id="synthetic-record",
    )
    assert result.envelope == original
    assert (result.current, result.migrated, result.external) == (0, 0, 1)
    with pytest.raises(CredentialResolutionError):
        CredentialResolver.migrate_local_envelope(result.envelope, scope=scope)


def test_migration_cli_rejects_retired_provider_before_opening_database(monkeypatch, capsys):
    monkeypatch.setattr(migration_cli, "settings", Settings(_env_file=None, CREDENTIAL_ENCRYPTION_PROVIDER="oci_kms"))

    def unexpected_database():
        raise AssertionError("Invalid provider must fail before opening a database")

    monkeypatch.setattr(migration_cli, "SessionLocal", unexpected_database)
    assert migration_cli.main() == 78
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "credential_migration_failed code=unsafe_credential_provider\n"


@pytest.mark.parametrize("external", [0, 1])
def test_migration_cli_distinguishes_unresolved_external_credentials(monkeypatch, capsys, external):
    monkeypatch.setattr(migration_cli, "settings", Settings(_env_file=None, CREDENTIAL_ENCRYPTION_PROVIDER="local"))
    monkeypatch.setattr(migration_cli, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(migration_cli, "migrate_local_credential_envelopes", lambda db:
                        migration_cli.CredentialMigrationResult(inspected=2 + external, migrated=1, current=1, external=external))
    assert migration_cli.main() == (78 if external else 0)
    captured = capsys.readouterr()
    status = "credential_migration_incomplete" if external else "credential_migration_complete"
    assert captured.out == f"{status} inspected={2 + external} migrated=1 current=1 external={external}\n"
    assert captured.err == ""
