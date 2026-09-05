from __future__ import annotations

import asyncio
import importlib

import pytest
from pydantic import SecretStr

from app.core.config import DEFAULT_APP_SECRET, Settings
from app.runtime.startup_security import StartupSecurityError, validate_startup_security
from app.services.runtime_boundary import get_resident_runtime_adapter


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "production",
        "APP_SECRET": SecretStr("synthetic-production-secret-for-tests"),
        "BROWSER_SESSION_ALLOWED_ORIGINS": "https://angmoo.com",
        "CREDENTIAL_ENCRYPTION_PROVIDER": "oci_kms",
        "OCI_KMS_KEY_ID": "synthetic-key-id",
        "OCI_KMS_CRYPTO_ENDPOINT": "https://synthetic.crypto.us-test-1.oraclecloud.com",
        "OCI_REGION": "us-test-1",
        "OCI_AUTH_MODE": "instance_principal",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _local_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "local",
        "APP_SECRET": SecretStr("synthetic-local-secret-for-tests"),
        "API_DOCS_ENABLED": False,
        "SIGNUP_ENABLED": False,
        "DATABASE_URL": "sqlite+pysqlite:///C:/synthetic/angmoo.sqlite3",
        "BROWSER_SESSION_ALLOWED_ORIGINS": "http://tauri.localhost",
        "DESKTOP_ALLOWED_ORIGIN": "http://tauri.localhost",
        "DESKTOP_LAUNCH_TOKEN": SecretStr("a" * 32),
        "CREDENTIAL_ENCRYPTION_PROVIDER": "local",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"APP_SECRET": SecretStr(DEFAULT_APP_SECRET)}, "unsafe_app_secret"),
        ({"CREDENTIAL_ENCRYPTION_PROVIDER": "local"}, "unsafe_credential_provider"),
        ({"CREDENTIAL_ENCRYPTION_PROVIDER": "dev"}, "unsafe_credential_provider"),
        ({"CREDENTIAL_ENCRYPTION_PROVIDER": "dev-v1"}, "unsafe_credential_provider"),
        ({"OCI_KMS_KEY_ID": None}, "missing_kms_config"),
        ({"OCI_KMS_CRYPTO_ENDPOINT": None}, "missing_kms_config"),
        ({"OCI_REGION": None}, "missing_kms_config"),
        (
            {"OCI_KMS_CRYPTO_ENDPOINT": "http://synthetic.invalid"},
            "invalid_kms_endpoint",
        ),
        (
            {"OCI_KMS_CRYPTO_ENDPOINT": "https://user:pass@synthetic.invalid"},
            "invalid_kms_endpoint",
        ),
        ({"OCI_AUTH_MODE": "config_file"}, "invalid_oci_auth_mode"),
    ],
)
def test_production_startup_rejects_unsafe_security_configuration(
    overrides: dict[str, object], expected_code: str
) -> None:
    with pytest.raises(StartupSecurityError) as exc_info:
        validate_startup_security(
            _production_settings(**overrides),
            kms_round_trip=lambda plaintext: plaintext,
        )

    assert exc_info.value.code == expected_code
    assert str(exc_info.value) == expected_code


def test_production_startup_accepts_matching_fake_kms_round_trip() -> None:
    observed: list[str] = []

    def round_trip(plaintext: str) -> str:
        observed.append(plaintext)
        return plaintext

    validate_startup_security(_production_settings(), kms_round_trip=round_trip)

    assert len(observed) == 1
    assert len(observed[0]) >= 32


def test_local_desktop_startup_accepts_embedded_security_contract() -> None:
    validate_startup_security(_local_settings())


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"APP_SECRET": SecretStr(DEFAULT_APP_SECRET)}, "unsafe_app_secret"),
        ({"CREDENTIAL_ENCRYPTION_PROVIDER": "oci_kms"}, "unsafe_credential_provider"),
        ({"DATABASE_URL": "postgresql+psycopg://localhost/angmoo"}, "local_database_required"),
        ({"DESKTOP_LAUNCH_TOKEN": SecretStr("too-short")}, "local_desktop_token_required"),
        ({"DESKTOP_ALLOWED_ORIGIN": "http://127.0.0.1:3000"}, "local_desktop_origin_invalid"),
        ({"API_DOCS_ENABLED": True}, "local_api_docs_forbidden"),
        ({"SIGNUP_ENABLED": True}, "local_signup_forbidden"),
    ],
)
def test_local_desktop_startup_rejects_drifted_security_configuration(
    overrides: dict[str, object], expected_code: str
) -> None:
    with pytest.raises(StartupSecurityError) as exc_info:
        validate_startup_security(_local_settings(**overrides))

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize("failure_mode", ["exception", "mismatch"])
def test_kms_preflight_fails_closed_without_exposing_probe_material(
    failure_mode: str,
) -> None:
    captured: list[str] = []

    def round_trip(plaintext: str) -> str:
        captured.append(plaintext)
        if failure_mode == "exception":
            raise RuntimeError(f"provider failed with {plaintext}")
        return "different-plaintext"

    with pytest.raises(StartupSecurityError) as exc_info:
        validate_startup_security(_production_settings(), kms_round_trip=round_trip)

    assert exc_info.value.code == "kms_preflight_failed"
    assert captured[0] not in str(exc_info.value)
    assert "synthetic-key-id" not in str(exc_info.value)


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_nonproduction_startup_does_not_probe_kms(app_env: str) -> None:
    called = False

    def probe(_: str) -> str:
        nonlocal called
        called = True
        raise AssertionError("KMS probe must not run outside production")

    validate_startup_security(
        Settings(_env_file=None, APP_ENV=app_env),
        kms_round_trip=probe,
    )

    assert called is False


def test_lifespan_security_failure_happens_before_database_seed_or_workers() -> None:
    main_module = importlib.import_module("app.main")
    calls: list[str] = []

    def fail_validation() -> None:
        calls.append("security")
        raise StartupSecurityError("kms_preflight_failed")

    def fail_database_session():
        calls.append("database")
        raise AssertionError("database must not be touched")

    lifespan = main_module.create_lifespan(
        getattr(main_module, "hosted_extension", None),
        security_validator=fail_validation,
        session_factory=fail_database_session,
    )

    async def run() -> None:
        async with lifespan(main_module.app):
            raise AssertionError("lifespan must not yield")

    with pytest.raises(StartupSecurityError, match="kms_preflight_failed"):
        asyncio.run(run())

    assert calls == ["security"]


def test_hosted_lifespan_registers_runtime_adapter_only_while_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = importlib.import_module("app.main")
    if not hasattr(main_module, "hosted_extension"):
        pytest.skip("hosted lifespan is not part of the public runtime profile")

    monkeypatch.setattr(main_module, "validate_startup_security", lambda: None)
    monkeypatch.setattr(main_module.settings, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(
        main_module.settings,
        "RESIDENT_TICK_SCHEDULER_ENABLED",
        False,
    )
    monkeypatch.setattr(
        main_module.settings,
        "POST_IMAGE_JOB_WORKER_ENABLED",
        False,
    )

    async def run() -> None:
        assert get_resident_runtime_adapter() is None
        async with main_module.lifespan(main_module.app):
            adapter = get_resident_runtime_adapter()
            assert adapter is not None
            assert adapter.name == "openclaw"
        assert get_resident_runtime_adapter() is None

    asyncio.run(run())
