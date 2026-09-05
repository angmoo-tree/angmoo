"""Character state admission and existing HTTP surface keep their write policy."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as registered_models
from app.api.v1.routes import community as community_routes
from app.core.unit_of_work import deferred_commits
from app.domains.characters import dependencies, exceptions, models, router, schemas
from app.domains.characters.service import profile, state
from app.services import community as legacy


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state-http.sqlite3'}", connect_args={"check_same_thread": False})
    for table in (registered_models.User.__table__, models.Character.__table__, models.CharacterState.__table__):
        table.create(engine)
    with Session(engine) as db:
        user = registered_models.User(id="owner", display_name="Owner")
        db.add(user)
        db.commit()
        character = profile.create_character(db, user=user, character_id="bird", data=schemas.AgentCreate(name="Bird", execution_mode="local"))
        yield db, user, character
    engine.dispose()


def test_state_service_keeps_owner_gate_legacy_error_and_deferred_write(database):
    db, owner, character = database
    data = schemas.CharacterStateWrite(mood="calm", summary="Rested", memory_note="private memory")
    with pytest.raises(exceptions.CharacterStateNotFoundError):
        state.save_character_state_for_user(db, SimpleNamespace(id="foreign"), character.id, data)
    with pytest.raises(legacy.CharacterNotFoundError) as error:
        legacy.save_character_state_for_user(db, SimpleNamespace(id="foreign"), character.id, data)
    assert type(error.value) is legacy.CharacterNotFoundError
    assert str(error.value) == character.id
    assert db.get(models.CharacterState, character.id) is None
    commits = []
    event.listen(db, "after_commit", lambda current: commits.append(current))
    with deferred_commits():
        result = state.save_character_state_for_user(db, owner, character.id, data)
        assert result.memory_note == "private memory"
        assert commits == []
    db.rollback()
    assert db.get(models.CharacterState, character.id) is None


def test_state_http_retains_url_owner_visibility_and_same_route(database):
    db, owner, character = database
    original = next(route for route in community_routes.router.routes if route.name == "save_character_state")
    canonical = next(route for route in router.state_router.routes if route.name == "save_character_state")
    assert original is canonical
    app = FastAPI()
    app.include_router(community_routes.router, prefix="/api/v1")
    app.dependency_overrides[dependencies.get_db] = lambda: db
    app.dependency_overrides[dependencies.get_current_user] = lambda: owner
    with TestClient(app) as client:
        response = client.post(f"/api/v1/characters/{character.id}/state", json={"mood": "calm", "summary": "Rested", "memory_note": "owner-only"})
        assert response.status_code == 200
        assert response.json()["memory_note"] == "owner-only"
        app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id="foreign")
        blocked = client.post(f"/api/v1/characters/{character.id}/state", json={"summary": "Tampered"})
        assert blocked.status_code == 404
        assert blocked.json() == {"detail": "Character not found"}
        assert db.get(models.CharacterState, character.id).summary == "Rested"
