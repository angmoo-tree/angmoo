from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v25_metadata, build_sqlite_baseline_metadata, sqlite_schema_contract_digest, create_schema_version_table
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import images_v26
import hashlib
import pytest
from datetime import datetime, timezone
from app.runtime.persistence.sqlite_schema import sqlite_schema_digest
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError
from app.runtime.migrations.sqlite_versions import registry


def test_fresh_and_frozen_v25_upgrade(tmp_path):
    register_models()
    for upgraded in (False, True):
        engine = create_engine(f"sqlite:///{tmp_path / str(upgraded)}")
        metadata = build_sqlite_v25_metadata() if upgraded else build_sqlite_baseline_metadata()
        metadata.create_all(engine)
        with engine.begin() as connection:
            create_schema_version_table(connection)
            if upgraded:
                assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(25).schema_digest
                before = images_v26.capture_delta(connection)
                images_v26.upgrade(connection)
                images_v26.verify_delta(connection, before)
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(26).schema_digest
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
            assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        engine.dispose()


def populated_v25(root):
    source=root/"canonical"/"generations"/"image-v25"/"angmoo.sqlite3"
    source.parent.mkdir(parents=True)
    metadata=build_sqlite_v25_metadata();engine=create_engine(f"sqlite:///{source}")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(metadata.tables["users"].insert().values(id="image-owner",display_name="Owner"))
        connection.execute(metadata.tables["characters"].insert().values(id="image-character",owner_id="image-owner",
            name="Image Character",handle="image-character",persona_summary="legacy"))
        connection.execute(metadata.tables["agent_image_generation_settings"].insert().values(
            character_id="image-character",image_generation_enabled=False,image_key_mode="disabled",
            encrypted_pollinations_api_key="legacy-scoped-ciphertext",visual_identity_prompt="legacy appearance"))
        connection.execute(metadata.tables["posts"].insert().values(id="legacy-post",author_character_id="image-character",
            author_name="Image Character",title="기존 제목",body="기존 본문"))
        connection.execute(metadata.tables["post_media"].insert().values(post_id="legacy-post",url="/media/posts/legacy.png",
            alt_text="legacy",model="legacy-model",prompt_hash="a"*64,key_source="user",byte_size=123,width=24,height=16))
        connection.execute(metadata.tables["post_image_generation_jobs"].insert().values(post_id="legacy-post",
            character_id="image-character",user_id="image-owner",source="routine",status="succeeded",
            image_model="legacy-model",image_prompt="legacy prompt",prompt_hash="a"*64,key_source="user"))
        create_schema_version_table(connection)
        manifest=load_sqlite_manifest(25)
        connection.exec_driver_sql("INSERT INTO angmoo_schema_version (singleton_key,schema_version,source_revision,source_migration_count,schema_digest,created_at) VALUES (1,25,?,?,?,?)",
            (manifest.source_revision,manifest.source_migration_count,sqlite_schema_digest(connection),encode_utc_timestamp(datetime.now(timezone.utc))))
    engine.dispose()
    return source


@pytest.mark.parametrize("fail",[False,True])
def test_populated_upgrade_preserves_original_generation_even_mid_ddl_failure(tmp_path,monkeypatch,fail):
    source=populated_v25(tmp_path)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    if fail:
        def interrupted(connection):
            connection.exec_driver_sql("ALTER TABLE post_media RENAME TO simulated_interrupted_media")
            raise RuntimeError("injected-during-ddl")
        monkeypatch.setitem(registry.MIGRATIONS,25,interrupted)
        with pytest.raises(SqliteCanonicalUpgradeError,match="step_failed"):
            SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(tmp_path),fallback_generation="image-v25").upgrade()
        assert not (tmp_path/"canonical"/"current-generation.json").exists()
        assert not list(source.parent.parent.glob(".*.tmp-*"))
    else:
        upgraded=SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(tmp_path),fallback_generation="image-v25").upgrade()
        assert upgraded.source_version==25 and upgraded.target_version==26 and upgraded.database_path!=source
        engine=create_engine(f"sqlite:///{upgraded.database_path}")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT encrypted_pollinations_api_key,visual_identity_prompt,generation_auto_enabled FROM agent_image_generation_settings").one()==("legacy-scoped-ciphertext","legacy appearance",0)
            assert connection.exec_driver_sql("SELECT url,model,prompt_hash FROM post_media").one()==("/media/posts/legacy.png","legacy-model","a"*64)
            assert connection.exec_driver_sql("SELECT image_prompt,status,intent_id FROM post_image_generation_jobs").one()==("legacy prompt","succeeded",None)
            assert connection.exec_driver_sql("SELECT title,body FROM posts").one()==("기존 제목","기존 본문")
            assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        engine.dispose()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
