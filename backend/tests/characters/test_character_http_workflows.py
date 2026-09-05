"""Character HTTP and workflow boundaries preserve owner/session/write contracts."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, object_session
from starlette.requests import Request

from app import models as registered_models
from app.api.identity_dependencies import get_current_user
from app.api.v1.routes import agents as mixed_routes
from app.core.db import get_db
from app.domains.characters import dependencies, exceptions, models, router, schemas
from app.domains.characters.contracts import CharacterManagementWorkflows
from app.domains.characters.service import management
from app.runtime.characters import management as runtime


def _unreachable(*args):
    raise AssertionError("unrelated workflow was called")


def _workflows(**changes):
    return CharacterManagementWorkflows(**{
        **{name: _unreachable for name in CharacterManagementWorkflows.__dataclass_fields__},
        **changes,
    })


def test_character_writes_reach_runtime_in_same_session_after_original_commits(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'character-entry.sqlite3'}")
    registered_models.User.__table__.create(engine)
    models.Character.__table__.create(engine)
    owner = SimpleNamespace(id="owner")
    calls = []
    with Session(engine) as db:
        db.add(registered_models.User(id=owner.id, display_name="Owner"))
        db.commit()
        event.listen(db, "after_commit", lambda current: calls.append(("commit", current)))
        def validate(data):
            assert calls == []
            calls.append(("validate", data))
        def created(current, actual_owner, character, data):
            assert current is db and actual_owner is owner
            assert object_session(character) is db
            assert [kind for kind, _ in calls] == ["validate", "commit", "commit"]
            assert character.promotion_usage_allowed is True
            return character
        callbacks = _workflows(validate_initial_activity=validate, after_create=created)
        character = management.create_agent(db, owner, schemas.AgentCreate(name="Owner Bird", execution_mode="local", promotion_usage_allowed=True), workflows=callbacks)
        calls.clear()
        def profile_changed(current, actual_owner, actual_character, media_changed):
            assert current is db and actual_owner is owner and actual_character is character
            assert calls == [("commit", db)]
            assert actual_character.one_liner == "changed"
            assert media_changed is False
            return actual_character
        assert management.update_profile(db, owner, character.id, schemas.AgentProfileUpdate(one_liner="changed"), workflows=replace(callbacks, after_profile=profile_changed)) is character
        with pytest.raises(exceptions.AgentNotFoundError):
            management.get_agent(db, SimpleNamespace(id="other"), character.id, workflows=callbacks)
    engine.dispose()


def test_shared_auth_override_and_original_route_order_work_for_character_http():
    assert dependencies.get_current_user is get_current_user
    assert dependencies.get_db is get_db
    original = next(route for route in mixed_routes.router.routes if route.name == "list_agents")
    canonical = next(route for route in router.router.routes if route.name == "list_agents")
    assert original is canonical
    paths = [route.path for route in mixed_routes.router.routes]
    assert paths.index("/agents/drafts/{draft_id}") < paths.index("/agents/{character_id}")
    assert canonical.unique_id == "list_agents_agents_get"
    app = FastAPI()
    app.include_router(mixed_routes.router, prefix="/api/v1")
    owner = SimpleNamespace(id="owner")
    class EmptySession:
        def scalars(self, query):
            return []
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = EmptySession
    app.state.character_management_workflows = lambda: _workflows()
    with TestClient(app) as client:
        response = client.get("/api/v1/agents")
    assert response.status_code == 200
    assert response.json() == []


def test_detail_limit_and_missing_runtime_configuration_are_explicit(monkeypatch):
    seen = []
    marker = object()
    monkeypatch.setattr(runtime, "_build_agent_detail", lambda db, character, **kwargs: seen.append((db, character, kwargs)) or marker)
    callbacks = runtime.build_character_management_workflows()
    db, character = object(), object()
    assert callbacks.build_detail(db, character) is marker
    assert callbacks.build_full_detail(db, character) is marker
    assert seen == [(db, character, {}), (db, character, {"recent_activity_limit": runtime.AGENT_DETAIL_ACTIVITY_LIMIT})]
    request = Request({"type": "http", "app": FastAPI()})
    with pytest.raises(RuntimeError, match="character management workflows are not configured"):
        dependencies.get_character_management_workflows(request)


def test_both_application_factories_install_workflows_and_schema_aliases_keep_identity():
    from app.main import create_app as create_hosted_app
    from app.public_main import create_app as create_public_app
    from app import schemas as aggregate_schemas
    from app.domains.identity.schemas import CredentialRead
    from app.domains.routines.schemas import AgentActivityLogRead, AgentSlotRead
    for factory in (create_hosted_app, create_public_app):
        app = factory()
        request = Request({"type": "http", "app": app})
        workflows = dependencies.get_character_management_workflows(request)
        assert workflows.build_detail is runtime._build_agent_detail
        assert workflows.after_create is runtime._after_character_created
    assert aggregate_schemas.AgentDetailRead is schemas.AgentDetailRead
    assert aggregate_schemas.CredentialRead is CredentialRead
    assert aggregate_schemas.AgentActivityLogRead is AgentActivityLogRead
    assert aggregate_schemas.AgentSlotRead is AgentSlotRead
