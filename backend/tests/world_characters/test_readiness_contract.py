"""Readiness preserves the shared DTO, readonly evaluation and error precedence."""
from types import SimpleNamespace
from datetime import UTC, datetime
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app import models
from app.core.db import Base
from app.domains.characters.schemas import AgentActivityProfileReadinessRead
from app.domains.world_characters.service.readiness import evaluate
from test_runtime_mode_repair import _user, _seed_world_scope, _seed_ready_entry


def test_readiness_keeps_shared_dto_and_world_scope_before_stale_profile():
    from app.schemas.agents import AgentActivityProfileReadinessRead as old_response
    assert old_response is AgentActivityProfileReadinessRead
    from app.domains.characters.schemas import AgentActivityProfileReadinessRead as character_response
    assert character_response is AgentActivityProfileReadinessRead
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(_user())
        db.flush()
        _seed_world_scope(db, "world-local")
        target = _seed_ready_entry(db, world_id="world-local", suffix="readiness")
        db.add(models.CharacterActiveWorld(character_id=target.character_id,
                    world_character_id=target.id, version=1,
                    selected_at=datetime.now(UTC), idempotency_key="select-readiness"))
        db.commit()
        character = db.get(models.Character, target.character_id)
        world = db.get(models.World, "world-local")
        world.status = "archived"
        target.character_contract_hash = "stale"
        db.commit()
        statements, writes = [], []
        event.listen(engine, "before_cursor_execute", lambda _c, _cu, statement, *_: statements.append(statement))
        event.listen(db, "after_flush", lambda *_: writes.append("flush"))
        event.listen(db, "after_commit", lambda *_: writes.append("commit"))
        result = evaluate(db, character=character, setting=SimpleNamespace())
        assert result.reason_code == "world_scope_not_ready"
        assert result.world_id == "world-local" and result.world_character_id == target.id
        assert result.source == "world_community_profile" and not result.ready
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        assert writes == []


def test_missing_active_world_retains_legacy_tendency_readiness():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        character = SimpleNamespace(id="not-selected")
        setting = SimpleNamespace(planner_tendency_profile={"feed_seed_interest_criteria":"interest"},
            tendency_updated_at=object(), tendency_summary="summary", tendency_action_ranges={"like":1})
        ready = evaluate(db, character=character, setting=setting)
        assert ready.model_dump() == {"ready":True,"source":"legacy_tendency","reason_code":None,
                                     "world_id":None,"world_character_id":None}
        setting.planner_tendency_profile = {"feed_seed_interest_criteria":" "}
        unready = evaluate(db, character=character, setting=setting)
        assert not unready.ready and unready.reason_code == "legacy_tendency_not_ready"
