"""Synthetic v33 transition: parity, authentication, preservation and staging."""
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from app.core import security
from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter, migration_secret_source
from app.runtime.migrations.sqlite_versions import image_provider_vault_v34 as migration
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_schema import build_sqlite_v33_metadata, create_schema_version_table, sqlite_schema_contract_digest, sqlite_schema_digest
from app.runtime.persistence.model_registration import register_models
from world_configuration_fixture_support import seed_configuration_fixture

SECRET="synthetic-vault-migration-secret"


def envelope(raw, provider, purpose="user_image"):
    return security.encrypt_local_secret(raw, scope=security.SecretScope(owner_id="fixture-owner", character_id="config-role-a", provider=provider, purpose=purpose),app_secret=SECRET)


def seed(path, *, corrupt=False):
    register_models()
    engine=seed_configuration_fixture(path,schema_metadata=build_sqlite_v33_metadata())
    with engine.begin() as c:
        create_schema_version_table(c)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(33).schema_digest
        values=dict(id="image",owner="fixture-owner",world="config-world-a",actor="config-role-a",secret=envelope(json.dumps({"version":"comfy-secrets.v1","key":"synthetic-server","partner":"synthetic-partner"}),"comfyui"))
        c.execute(text("INSERT INTO world_credentials (id,owner_id,world_id,world_character_id,purpose,provider,model,revision,aad_character_id,aad_purpose,encrypted_secret) VALUES (:id,:owner,:world,:actor,'image','comfyui','workflow',4,:actor,'user_image',:secret)"),values)
        for revision,provider,secret in [(1,"novelai",envelope("synthetic-novel","novelai")),(2,"openrouter",None),(3,"comfyui",values['secret']),(4,"comfyui",values['secret'])]:
            c.execute(text("INSERT INTO world_credential_revisions (credential_id,revision,provider,model,aad_character_id,aad_purpose,encrypted_secret) VALUES ('image',:revision,:provider,:model,'config-role-a','user_image',:secret)"),
                dict(revision=revision,provider=provider,model="workflow" if provider=="comfyui" else "nai-diffusion-4-5-full" if provider=="novelai" else "openai/gpt-image-2.5-flare",secret="corrupt-envelope" if corrupt and revision==3 else secret))
        for purpose,raw in [("user_image","synthetic-server"),("comfy_partner_image","synthetic-partner")]:
            c.execute(text("INSERT INTO media_credentials (id,owner_id,character_scope,provider,purpose,encrypted_secret,fingerprint,revision,enabled) VALUES (:id,'fixture-owner','config-role-a','comfyui',:purpose,:secret,'old-fingerprint',1,1)"),
                dict(id=purpose,purpose=purpose,secret=envelope(raw,"comfyui",purpose)))
        m=load_sqlite_manifest(33)
        c.exec_driver_sql("INSERT INTO angmoo_schema_version VALUES(1,33,?,?,?,?)",(m.source_revision,m.source_migration_count,sqlite_schema_digest(c),datetime.now(UTC).isoformat()))
    return engine


@pytest.mark.parametrize("alembic",[False,True])
def test_authenticated_forward_schema_parity_and_idempotence(tmp_path,alembic,deny_external_network):
    e=seed(tmp_path/'v33.sqlite3'); interpreter=MigrationSecretInterpreter(secret_source=lambda:SECRET)
    with e.begin() as c:
        before=migration.capture_delta(c)
        partner_before=c.exec_driver_sql("SELECT encrypted_secret FROM media_credentials WHERE purpose='comfy_partner_image'").scalar_one()
        if alembic:
            path=Path(__file__).parents[2]/'alembic/versions/20261009_0111_image_provider_vault.py'
            spec=importlib.util.spec_from_file_location('image_vault_migration',path); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            mod.op=Operations(MigrationContext.configure(c))
            with migration_secret_source(lambda:SECRET): mod.upgrade()
        else: migration.upgrade(c,interpreter=interpreter)
        migration.verify_delta(c,before)
        assert sqlite_schema_contract_digest(c)==load_sqlite_manifest(34).schema_digest
        assert c.exec_driver_sql("SELECT count(*) FROM world_image_provider_credentials").scalar()==3
        assert c.exec_driver_sql("SELECT enabled,tombstone FROM world_image_provider_credentials WHERE provider='openrouter'").one()==(0,1)
        assert c.exec_driver_sql("SELECT encrypted_secret FROM media_credentials WHERE purpose='comfy_partner_image'").scalar_one()==partner_before
        for cipher in c.exec_driver_sql("SELECT encrypted_secret FROM world_credential_revisions WHERE provider='comfyui'").scalars():
            raw=security.decrypt_local_secret(cipher,scope=security.SecretScope(owner_id='fixture-owner',character_id='config-role-a',provider='comfyui',purpose='user_image'),app_secret=SECRET)
            assert json.loads(raw)==dict(version='comfy-secrets.v1',key='',partner='synthetic-partner')
        vault_before=c.exec_driver_sql("SELECT * FROM world_image_provider_credentials ORDER BY id").all()
        migration.upgrade(c,interpreter=interpreter)
        assert c.exec_driver_sql("SELECT * FROM world_image_provider_credentials ORDER BY id").all()==vault_before
        assert not c.exec_driver_sql("PRAGMA foreign_key_check").all()
    e.dispose()


@pytest.mark.parametrize("failure",[None,"wrong-secret","corrupt"])
def test_staged_upgrade_preserves_source_and_rolls_back_auth_failure(tmp_path,failure,deny_external_network):
    path=tmp_path/'canonical/generations/vault-v33/angmoo.sqlite3';path.parent.mkdir(parents=True)
    seed(path,corrupt=failure=='corrupt').dispose();before=hashlib.sha256(path.read_bytes()).hexdigest()
    interpreter=MigrationSecretInterpreter(secret_source=lambda:'wrong' if failure=='wrong-secret' else SECRET)
    coordinator=SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(tmp_path),fallback_generation='vault-v33',secret_interpreter=interpreter)
    if failure:
        with pytest.raises(SqliteCanonicalUpgradeError,match='image_vault_secret_authentication_failed'): coordinator.upgrade()
        assert not (tmp_path/'canonical/current-generation.json').exists()
        assert not list(path.parent.parent.glob('.*.tmp-*'))
    else:
        result=coordinator.upgrade();assert result.source_version==33 and result.target_version==34
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
