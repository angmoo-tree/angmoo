from __future__ import annotations

import asyncio
import importlib

import pytest
from pydantic import SecretStr

from app.config import DEFAULT_APP_SECRET, Settings
from app.runtime.startup_security import StartupSecurityError, validate_startup_security
from app.runtime.extensions.resident_adapter import get_resident_runtime_adapter


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "production",
        "APP_SECRET": SecretStr("synthetic-production-secret-for-tests"),
        "BROWSER_SESSION_ALLOWED_ORIGINS": "https://angmoo.com",
        "CREDENTIAL_ENCRYPTION_PROVIDER": "oci_kms",
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


@pytest.mark.parametrize("provider", ["oci_kms", "oci-kms", "local", "dev"])
def test_retired_hosted_startup_is_not_reenabled_by_removing_kms(
    provider: str, deny_external_network,
) -> None:
    with pytest.raises(StartupSecurityError) as exc_info:
        validate_startup_security(
            _production_settings(CREDENTIAL_ENCRYPTION_PROVIDER=provider),
        )

    assert exc_info.value.code == "unsupported_runtime_profile"
    assert str(exc_info.value) == "unsupported_runtime_profile"


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


@pytest.mark.parametrize("app_env", ["development", "test"])
@pytest.mark.parametrize("provider", ["local", "dev", "local-v2"])
def test_supported_startup_keeps_local_aliases_without_external_calls(
    app_env: str, provider: str, deny_external_network,
) -> None:
    validate_startup_security(
        Settings(_env_file=None, APP_ENV=app_env, CREDENTIAL_ENCRYPTION_PROVIDER=provider),
    )


@pytest.mark.parametrize("app_env", ["development", "test"])
@pytest.mark.parametrize("provider", ["oci_kms", "oci-kms", "dev-v1", "synthetic-unsupported-value"])
def test_direct_startup_rejects_unsupported_provider_without_leaking_value(
    app_env: str, provider: str, deny_external_network,
) -> None:
    with pytest.raises(StartupSecurityError) as exc_info:
        validate_startup_security(
            Settings(_env_file=None, APP_ENV=app_env, CREDENTIAL_ENCRYPTION_PROVIDER=provider),
        )
    assert exc_info.value.code == "unsafe_credential_provider"
    assert str(exc_info.value) == "unsafe_credential_provider"


def test_lifespan_security_failure_happens_before_database_seed_or_workers() -> None:
    main_module = importlib.import_module("app.main")
    calls: list[str] = []

    def fail_validation() -> None:
        calls.append("security")
        validate_startup_security(_production_settings())

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

    with pytest.raises(StartupSecurityError, match="unsupported_runtime_profile"):
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
