import json

import pytest
from sqlalchemy import create_engine

from app.runtime.migrations.sqlite_versions import world_activity_v30
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v29_metadata, create_schema_version_table, sqlite_schema_contract_digest


def test_v29_to_v30_schema_parity_and_idempotent_empty_transition(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'v29.sqlite3'}")
    build_sqlite_v29_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(29).schema_digest
        before = world_activity_v30.capture_delta(connection)
        world_activity_v30.upgrade(connection)
        world_activity_v30.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(30).schema_digest
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        world_activity_v30.upgrade(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(30).schema_digest
    engine.dispose()


def test_historical_manifest_hashes_remain_attested():
    assert load_sqlite_manifest(28).schema_digest == "19263f9b90e8827364078a594f8466811e895cb6ce4396ab817dd8b9db5e23fa"
    assert load_sqlite_manifest(29).schema_digest == load_sqlite_manifest(28).schema_digest


def populated_v29(tmp_path, *, invalid_key=False, duplicate_key=False):
    from sqlalchemy.orm import Session
    from app.core import security
    from app.domains.identity.models import LlmCredential
    from app.domains.identity.models_media import MediaCredential
    from app.domains.characters.models import AgentImageGenerationSetting
    from app.domains.memory.models.batch import MemoryBatchProfile
    from app.domains.world_characters.models import WorldCharacter
    from memory.test_p8_l_o_memory_consolidation import _stack
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'populated-v29.sqlite3'}")
    build_sqlite_v29_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
    with Session(engine) as db:
        scope, setting, *_ = _stack(db)
        character = db.get(WorldCharacter, scope.subject_world_character_id).character_id
        aad = security.SecretScope(owner_id=scope.owner_id, character_id=character, provider="google", purpose="agent")
        encrypted = "invalid-envelope" if invalid_key else security.encrypt_secret("synthetic-sns-key", scope=aad)
        db.add(LlmCredential(id="own-legacy-sns", owner_id=scope.owner_id, character_id=character,
            provider="google", purpose="agent", model="gemini-3.1-flash-lite", thinking_level="high",
            auth_profile_id="test-original", label="original", enabled=True, encrypted_api_key=encrypted))
        if duplicate_key:
            db.add(LlmCredential(id="ambiguous-legacy-sns", owner_id=scope.owner_id, character_id=character,
                provider="google", purpose="agent", model="gemini-3.1-flash-lite", thinking_level="medium",
                auth_profile_id="test-ambiguous", label="ambiguous", enabled=True, encrypted_api_key=encrypted))
        db.add(LlmCredential(id="global-chat-key", owner_id=scope.owner_id, character_id=None,
            provider="google", purpose="chat", model="gemini-3.1-flash-lite", auth_profile_id="test-global", label="global",
            enabled=True, encrypted_api_key=encrypted))
        for purpose, raw in (("user_image", "synthetic-comfy-server"), ("comfy_partner_image", "synthetic-comfy-partner")):
            envelope = security.encrypt_secret(raw, scope=security.SecretScope(owner_id=scope.owner_id, character_id=character, provider="comfyui", purpose=purpose))
            db.add(MediaCredential(id=purpose, owner_id=scope.owner_id, character_scope=character, provider="comfyui",
                purpose=purpose, enabled=True, revision=4, encrypted_secret=envelope))
        profile = {"active": True, "options": {"base_url": "http://127.0.0.1:8188", "partner_auth": True}, "connection": {"ready": True}, "reference_enabled": False}
        db.add(AgentImageGenerationSetting(character_id=character, generation_provider="comfyui", generation_model="workflow",
            generation_profiles_json=json.dumps({"comfyui:workflow:": profile}), generation_auto_enabled=True,
            generation_daily_limit=12, appearance_prompt="whole appearance", style_prompt="whole style", negative_prompt="whole negative"))
        db.add(MemoryBatchProfile(owner_id=scope.owner_id, model_id="gemini-3.1-flash-lite", thinking_level="high", version=3))
        db.commit()
        sid = setting.id
    return engine, scope, sid, character


def test_populated_transition_keeps_original_aad_configuration_and_independent_profiles(tmp_path, deny_external_network):
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
    from app.domains.identity.service import world_credentials
    from app.domains.media.models_world_policy import WorldImagePolicy
    from app.domains.memory.models.activity_configuration import MemorySubjectProfile
    engine, scope, sid, character = populated_v29(tmp_path)
    with engine.begin() as connection, world_activity_v30.secret_interpreter(MigrationSecretInterpreter()):
        before = world_activity_v30.capture_delta(connection)
        old = tuple(connection.execute(text("SELECT encrypted_api_key FROM llm_credentials ORDER BY id")))
        world_activity_v30.upgrade(connection)
        world_activity_v30.verify_delta(connection, before)
        assert tuple(connection.execute(text("SELECT encrypted_api_key FROM llm_credentials ORDER BY id"))) == old
        world_activity_v30.upgrade(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(30).schema_digest
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    with Session(engine) as db:
        kwargs = dict(owner_id=scope.owner_id, world_id=scope.world_id, world_character_id=scope.subject_world_character_id)
        assert world_credentials.resolve(db, **kwargs, purpose="sns").reveal() == "synthetic-sns-key"
        assert world_credentials.find(db, **kwargs, purpose="sns").aad_character_id == character
        image, partner = world_credentials.resolve_image_keys(db, **kwargs)
        assert image.reveal() == "synthetic-comfy-server" and partner == "synthetic-comfy-partner"
        assert not world_credentials.find(db, **kwargs, purpose="chat")
        policy = db.get(WorldImagePolicy, scope.subject_world_character_id)
        assert policy.generation_limit == 12 and policy.vision_limit is None and not policy.vision_enabled
        assert policy.generation_settings["appearance"] == "whole appearance"
        assert policy.generation_settings["negative"] == "whole negative"
        assert policy.generation_settings["profiles"]["comfyui:workflow"]["options"]["partner_auth"]
        assert db.get(MemorySubjectProfile, sid).version == 3
    engine.dispose()


@pytest.mark.parametrize("interpreter", [None, "invalid"])
def test_missing_or_wrong_secret_proof_stops_before_schema_changes(tmp_path, interpreter):
    from sqlalchemy import inspect
    from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
    from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError
    engine, *_ = populated_v29(tmp_path, invalid_key=interpreter == "invalid")
    with engine.begin() as connection, world_activity_v30.secret_interpreter(None if interpreter is None else MigrationSecretInterpreter()):
        old = sqlite_schema_contract_digest(connection)
        with pytest.raises(SqliteMigrationDeltaError, match="secret_interpreter_required|secret_authentication_failed"):
            world_activity_v30.upgrade(connection)
        assert sqlite_schema_contract_digest(connection) == old
        assert not world_activity_v30.NEW_TABLES.intersection(inspect(connection).get_table_names())
    engine.dispose()


def test_ambiguous_original_keys_are_preserved_for_reentry_instead_of_arbitrarily_selected(tmp_path):
    from sqlalchemy import text
    from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
    engine, scope, *_ = populated_v29(tmp_path, duplicate_key=True)
    with engine.begin() as connection, world_activity_v30.secret_interpreter(MigrationSecretInterpreter()):
        world_activity_v30.upgrade(connection)
        assert connection.execute(text("SELECT count(*) FROM llm_credentials WHERE character_id IS NOT NULL")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM world_credentials WHERE world_character_id=:id AND purpose='sns'"), {"id": scope.subject_world_character_id}).scalar_one() == 0
    engine.dispose()


def test_local_comfy_partner_only_is_migrated_without_inventing_a_primary_key(tmp_path, deny_external_network):
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
    from app.domains.identity.service import world_credentials
    engine, scope, *_ = populated_v29(tmp_path)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM media_credentials WHERE purpose='user_image'"))
    with engine.begin() as connection, world_activity_v30.secret_interpreter(MigrationSecretInterpreter()):
        world_activity_v30.upgrade(connection)
    with Session(engine) as db:
        kwargs = dict(owner_id=scope.owner_id, world_id=scope.world_id, world_character_id=scope.subject_world_character_id)
        value = world_credentials.metadata(world_credentials.find(db, **kwargs, purpose="image"), purpose="image")
        assert not value.has_key and value.has_partner_key
        primary, partner = world_credentials.resolve_image_keys(db, **kwargs)
        assert primary.reveal() == "" and partner == "synthetic-comfy-partner"
    engine.dispose()
