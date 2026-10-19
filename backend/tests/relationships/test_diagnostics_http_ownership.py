from fastapi import FastAPI, Request
from fastapi.routing import _iter_routes_with_context
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import identity_dependencies
from app.api.v1.routes import world_activity_runtime
from app.config import Settings, settings
from app.domains.relationships import dependencies
from app.runtime.graph_projection import composition, diagnostic_references
from p7_graph_support import seed_projection_fixture, sqlite_engine
from identity.test_world_credentials import world_session, write


def test_both_factories_bind_relationship_readers_and_register_each_route_once():
    from app.main import create_app as hosted
    from app.main import create_public_app as local

    for factory in (hosted, local):
        app = factory()
        request = Request({"type": "http", "app": app})
        session = object()
        readers = dependencies.get_read_references(request, session)
        assert isinstance(readers, diagnostic_references.SqlAlchemyDiagnosticReferences)
        assert readers.db is session
        # The hosted factory historically uses the global fallback until startup.
        assert readers.config is getattr(app.state, "runtime_settings", settings)
        request_config = Settings(GRAPH_PROJECTION_ENABLED=False)
        app.state.runtime_settings = request_config
        assert dependencies.get_read_references(request, session).config is request_config
        routes = [route for route, _ in _iter_routes_with_context(app.routes)]
        owned = [route for route in routes if getattr(getattr(route, "endpoint", None), "__module__", "") == "app.domains.relationships.router"]
        assert len(owned) == 3
        assert [route.name for route in owned] == [
            "get_world_character_social_memory", "get_world_character_relationship_graph", "get_relationship_review"
        ]
    assert dependencies.get_current_user is identity_dependencies.get_current_user


def test_real_diagnostics_http_preserves_session_owner_errors_and_graph_validation(monkeypatch):
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="diagnostics-http")
        app = FastAPI()
        app.state.runtime_settings = Settings(GRAPH_PROJECTION_ENABLED=False)
        composition.configure_relationships_runtime(app)
        app.include_router(world_activity_runtime.router, prefix="/api/v1")
        app.dependency_overrides[dependencies.get_db] = lambda: db
        app.dependency_overrides[dependencies.get_current_user] = lambda: fixture.owner
        calls = []
        original = diagnostic_references.get_character

        def get_character(session, character_id):
            calls.append((session, character_id))
            return original(session, character_id)

        monkeypatch.setattr(diagnostic_references, "get_character", get_character)
        client = TestClient(app)
        prefix = f"/api/v1/characters/{fixture.actor.id}/worlds/{fixture.world.id}"
        response = client.get(prefix + "/social-memory")
        assert response.status_code == 200
        assert response.json()["world_character_id"] == fixture.actor_world_character.id
        assert response.json()["relationship_graph_status"] == "disabled"
        assert calls == [(db, fixture.actor.id)]

        graph = client.get(prefix + "/relationship-graph")
        assert graph.status_code == 200
        assert graph.json()["meta"]["source"] == "canonical_fallback"
        invalid = client.get(prefix + "/relationship-graph?depth=3")
        assert invalid.status_code == 422

        app.dependency_overrides[dependencies.get_current_user] = lambda: fixture.other_owner
        denied = client.get(prefix + "/social-memory")
        assert denied.status_code == 403
        assert denied.json() == {"detail": "character_not_owned"}
        absent = client.get(f"/api/v1/characters/missing/worlds/{fixture.world.id}/social-memory")
        assert absent.status_code == 404
        assert absent.json() == {"detail": "world_character_not_found"}
        assert fixture.event.retrieval_status == "eligible"
        assert fixture.outbox.status == "pending"
    engine.dispose()


def review_setting(db):
    from app.domains.memory.models.items import MemoryScopeSettingModel
    from app.domains.memory.models.batch import MemoryBatchSetting
    from app.domains.memory.models.activity_configuration import MemorySubjectProfile
    from datetime import UTC, datetime
    setting = MemoryScopeSettingModel(id="review-setting", owner_id="fixture-owner", world_id="config-world-a",
        subject_world_character_id="config-role-a", enabled=True)
    db.add(setting)
    db.flush()
    batch = MemoryBatchSetting(scope_setting_id=setting.id, ai_enabled=True, consent_version="synthetic-consent",
        schedule_enabled=True, local_time="05:20", timezone="Pacific/Honolulu")
    profile = MemorySubjectProfile(scope_setting_id=setting.id, model_id="gemini-3.1-flash-lite", thinking_level="high",
        updated_at=datetime.now(UTC))
    db.add_all([batch, profile])
    db.flush()
    return setting, batch, profile


def test_review_configuration_uses_exact_subject_purpose_model_and_current_timezone_without_writes(world_session):
    from sqlalchemy import event
    from app.domains.identity.service import world_credentials
    from app.domains.identity.models_environment import LocalEnvironment
    db = world_session
    setting, batch, profile = review_setting(db)
    environment = db.get(LocalEnvironment, setting.owner_id)
    assert environment is not None
    environment.timezone = "UTC"
    db.flush()
    reader = diagnostic_references.SqlAlchemyDiagnosticReferences(db, Settings())
    scope = dict(owner_id=setting.owner_id, world_id=setting.world_id, world_character_id=setting.subject_world_character_id)
    statements = []

    def record(_conn, _cursor, sql, *_rest):
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            statements.append(sql)

    def read():
        db.flush()
        event.listen(db.get_bind(), "before_cursor_execute", record)
        try:
            return reader.review_configuration(world_id=setting.world_id, actor_id=setting.subject_world_character_id)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record)

    assert read()["status"] == "consolidation_configuration_required"
    world_credentials.save(db, **{**scope, "world_id": "config-world-b", "world_character_id": "config-role-b"}, purpose="consolidation", data=write())
    world_credentials.save(db, **scope, purpose="chat", data=write())
    assert read()["status"] == "consolidation_configuration_required"
    world_credentials.save(db, **scope, purpose="consolidation", data=write())
    assert read() == {"status": "scheduled", "manual_available": True, "local_time": "05:20", "timezone": "UTC"}
    environment.preferred_language, environment.timezone = "en", "Asia/Seoul"
    assert read()["timezone"] == "Asia/Seoul"
    assert batch.timezone == "Pacific/Honolulu"
    world_credentials.save(db, **scope, purpose="consolidation", data=write(1, None, thinking="medium"))
    assert read()["status"] == "consolidation_configuration_required"
    profile.thinking_level = "medium"
    assert read()["status"] == "scheduled"
    batch.schedule_enabled = False
    assert read() == {"status": "schedule_disabled", "manual_available": True}
    world_credentials.delete(db, **scope, purpose="consolidation", expected_revision=2)
    assert read() == {"status": "consolidation_configuration_required", "manual_available": False}
    assert statements == []


def test_review_configuration_keeps_memory_consent_and_schedule_gates(world_session):
    from app.domains.identity.service import world_credentials
    db = world_session
    setting, batch, _profile = review_setting(db)
    reader = diagnostic_references.SqlAlchemyDiagnosticReferences(db, Settings())

    def read():
        db.flush()
        return reader.review_configuration(world_id=setting.world_id, actor_id=setting.subject_world_character_id)

    setting.enabled = False
    assert read() == {"status": "memory_disabled"}
    setting.enabled, batch.ai_enabled = True, False
    assert read() == {"status": "consent_or_ai_required"}
    batch.ai_enabled, batch.consent_version = True, None
    assert read() == {"status": "consent_or_ai_required"}
    batch.consent_version = "synthetic-consent"
    batch.schedule_enabled = False
    assert read() == {"status": "consolidation_configuration_required", "manual_available": False}
    world_credentials.save(db, owner_id=setting.owner_id, world_id=setting.world_id,
        world_character_id=setting.subject_world_character_id, purpose="consolidation", data=write())
    assert read() == {"status": "schedule_disabled", "manual_available": True}
