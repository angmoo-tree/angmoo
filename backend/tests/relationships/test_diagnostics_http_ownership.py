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


def test_both_factories_bind_relationship_readers_and_register_each_route_once():
    from app.main import create_app as hosted
    from app.public_main import create_app as local

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
        assert len(owned) == 2
        assert [route.name for route in owned] == [
            "get_world_character_social_memory", "get_world_character_relationship_graph"
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
