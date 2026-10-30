"""Official runtime profiles retain their owned local encryption configuration."""
from pydantic import SecretStr
import pytest

from app.config import Settings
from app.core import security
from app.runtime.configuration import RuntimeProfile, build_embedded_runtime_config, settings_from_runtime_config
from app.runtime.startup_security import validate_startup_security


@pytest.mark.parametrize("profile", list(RuntimeProfile))
def test_official_profiles_use_owned_local_key_despite_retired_parent_settings(
    profile, tmp_path, monkeypatch, deny_external_network,
):
    data_root = tmp_path / "owned-data"
    secret_file = data_root / "secrets/app-secret"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("synthetic-owned-local-key\n", encoding="utf-8")
    original = secret_file.read_bytes()
    if profile in {RuntimeProfile.EXPERIMENT_POSTGRESQL, RuntimeProfile.CONTRIBUTOR_POSTGRESQL, RuntimeProfile.LOCAL_POSTGRESQL}:
        import json
        from sqlalchemy import URL
        from app.runtime import postgresql_runtime, postgresql_experiment
        directory=data_root/'runtime';directory.mkdir()
        experiment=profile is RuntimeProfile.EXPERIMENT_POSTGRESQL
        marker=({'run_id':postgresql_experiment.RUN_ID,'source_sha':postgresql_experiment.SOURCE_SHA} if experiment
            else {'schema':'angmoo-postgresql-runtime.v1','installation_id':'synthetic-installation'})
        (directory/'postgresql-runtime.json').write_text(json.dumps(marker))
        dsn=URL.create('postgresql+psycopg',username='angmoo_pg_run01_admin' if experiment else 'synthetic_runtime',
            password='synthetic-only',host='127.0.0.1',port=15414,
            database='angmoo_pg_run01' if experiment else 'synthetic_db').render_as_string(hide_password=False)
        if experiment:
            config=postgresql_experiment.build_config(data_root,dsn)
        else:
            config=postgresql_runtime.build_config(data_root,dsn,
                desktop_launch_token='a'*32 if profile is RuntimeProfile.LOCAL_POSTGRESQL else '',
                frontend_origin='http://tauri.localhost' if profile is RuntimeProfile.LOCAL_POSTGRESQL else 'http://127.0.0.1:3000')
    else:
        config = build_embedded_runtime_config(
            profile=profile, data_root=data_root, runtime_root=data_root / "runtime",
            generation="synthetic-generation", desktop_launch_token="a" * 32,
            desktop_allowed_origin="http://tauri.localhost",
        )
    parent = Settings(
        _env_file=None, APP_ENV="production", CREDENTIAL_ENCRYPTION_PROVIDER="oci_kms",
        APP_SECRET=SecretStr("wrong-process-key"), APP_SECRET_FILE=str(tmp_path / "missing-secret"),
    )
    before = parent.model_dump()
    resolved = settings_from_runtime_config(config, base=parent)
    validate_startup_security(resolved)
    assert resolved.credential_encryption_provider == "local"
    assert resolved.app_secret == "synthetic-owned-local-key"
    monkeypatch.setattr(security, "settings", resolved)
    scope = security.SecretScope(owner_id="owner", character_id="character", provider="google", purpose="agent")
    ciphertext = security.encrypt_secret("synthetic-api-key", scope=scope)
    assert security.decrypt_local_secret(ciphertext, scope=scope, app_secret="synthetic-owned-local-key") == "synthetic-api-key"
    assert parent.model_dump() == before
    assert secret_file.read_bytes() == original
