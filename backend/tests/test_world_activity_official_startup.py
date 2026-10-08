"""Official composition, isolated SQLite/Ladybug startup and authenticated reads."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.runtime.contributor_backend import create_contributor_runtime_app
from app.runtime.persistence.sqlite_schema import sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.domains.identity.dependencies import get_current_user
from app.domains.identity.models import InstallationIdentity
from app.domains.characters.models import Character
from app.domains.identity.models_world_credentials import WorldCredential
from app.domains.media.models_world_policy import WorldImagePolicy
from chat.test_p8_l_d_world_chat_api import _seed, FRONTEND_HEADERS


def test_official_factory_cold_start_read_only_settings_health_and_restart(tmp_path, deny_external_network):
    root = tmp_path / "explicit-isolated-runtime"
    app = create_contributor_runtime_app(data_root=root)
    principal = {}
    with TestClient(app, base_url="http://127.0.0.1:3000") as client:
        assert client.get("/health").status_code == 200
        factory = app.state.runtime_composition.session_factory
        engine = factory.kw["bind"]
        owner, _, _ = _seed(engine, principal, existing_identity=True)
        with factory() as db:
            db.get(Character, "responding-character").owner_id = owner.id
            db.commit()
        app.dependency_overrides[get_current_user] = lambda: owner
        prefix = "/api/v1/worlds/world-a/world-characters/wc-responding"
        with engine.connect() as connection:
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(32).schema_digest
        with factory() as db:
            before = (db.scalar(select(func.count()).select_from(WorldCredential)),
                [(p.world_character_id, p.revision, p.generation_enabled, p.vision_enabled) for p in db.scalars(select(WorldImagePolicy))])
        for suffix in ("status", "settings", "credentials/chat", "credentials/vision",
            "credentials/consolidation", "credentials/embedding", "image-policy", "memory/embedding-settings", "memory/batch-settings"):
            response = client.get(f"{prefix}/{suffix}", headers=FRONTEND_HEADERS)
            assert response.status_code == 200, (suffix, response.text)
            assert "synthetic" not in response.text
        with factory() as db:
            after = (db.scalar(select(func.count()).select_from(WorldCredential)),
                [(p.world_character_id, p.revision, p.generation_enabled, p.vision_enabled) for p in db.scalars(select(WorldImagePolicy))])
            assert after == before and not db.new and not db.dirty
            p = db.get(WorldImagePolicy, "wc-responding")
            assert (p.generation_limit, p.vision_limit) == (20, 10)
    restored = create_contributor_runtime_app(data_root=root)
    with TestClient(restored, base_url="http://127.0.0.1:3000") as client:
        assert client.get("/health").status_code == 200
        factory = restored.state.runtime_composition.session_factory
        with factory() as db:
            p = db.get(WorldImagePolicy, "wc-responding")
            assert (p.generation_limit, p.vision_limit) == (20, 10)
        assert restored.state.runtime_config.data_paths.root == root.resolve()
