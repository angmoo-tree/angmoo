"""Activity resource routes use the same request Session and original response contracts."""
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from model_fixture_support import models as _registered_models
from app.api.identity_dependencies import get_current_user
from app.api.v1.routes.agents import router
from app.database import get_db
from app.domains.identity.models import User
from app.domains.characters.models import Character
from app.domains.routines.models import AgentActivitySetting
from app.domains.routines.exceptions import TendencyAnalysisParseError
from app.runtime.characters.management import build_activity_management_references, configure_character_activity_http


@pytest.mark.parametrize("operation", ["settings", "tendency"])
def test_activity_resource_http_preserves_route_owner_and_request_session(tmp_path: Path, operation: str) -> None:
    expected = {"get_feed_cue", "give_feed_cue", "get_settings", "update_settings", "analyze_tendency", "activate_agent", "deactivate_agent", "run_now", "first_greeting"}
    actual = {route.name: route for route in router.routes if route.name in expected}
    assert set(actual) == expected
    assert all(route.endpoint.__module__ == "app.domains.characters.router" for route in actual.values())
    engine = create_engine(f"sqlite:///{tmp_path / 'activity-http.sqlite3'}", connect_args={"check_same_thread": False})
    for table in (User.__table__, Character.__table__, AgentActivitySetting.__table__):
        table.create(engine)
    try:
        with Session(engine) as db:
            user = User(id="owner", display_name="owner")
            character = Character(id="character", owner_id="owner", name="character", handle="activity-http", persona_summary="fixture", execution_mode="llm")
            db.add_all([user, character])
            db.commit()
            calls = []
            app = FastAPI()
            app.include_router(router, prefix="/api/v1")
            configure_character_activity_http(app)
            def request_db():
                yield db
            app.dependency_overrides[get_db] = request_db
            app.dependency_overrides[get_current_user] = lambda: user
            def owned(current, principal, character_id):
                assert current is db and principal is user
                assert character_id == "character"
                calls.append("owned")
                return character
            app.state.activity_management_references = lambda: replace(build_activity_management_references(), get_owned_character=owned)
            async def analyze(current, principal, character_id):
                assert current is db and principal is user
                assert character_id == "character"
                calls.append("analysis")
                raise TendencyAnalysisParseError("synthetic internal parse details")
            app.state.tendency_analysis_runner = lambda: analyze
            with TestClient(app) as client:
                if operation == "settings":
                    response = client.get("/api/v1/agents/character/settings")
                    assert response.status_code == 200
                    assert response.json()["character_id"] == "character"
                    assert calls == ["owned"]
                    with Session(engine) as observer:
                        assert observer.get(AgentActivitySetting, "character") is not None
                else:
                    response = client.post("/api/v1/agents/character/tendency/analyze")
                    assert response.status_code == 502
                    assert response.json() == {"detail": "성향 분석 결과를 정리하지 못했습니다. 잠시 후 다시 시도해주세요."}
                    assert calls == ["analysis"]
    finally:
        engine.dispose()
