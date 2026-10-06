from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.domains.world_characters.service.activity_state import read_state, settle_state
from app.domains.world_characters.service.activity_engines import bind_run, resolve_engine, set_engine
from app.domains.characters.models import Character
from app.runtime.world_characters.creation_configuration import initialize_created_world_character
from world_characters.test_persona_continuity import _approved, _engine


def _restored_policy(db, actor, *, scope):
    """Historical DB input, never a supported API for creating current policy."""
    from app.domains.world_characters.activity_models import ActivityEnginePolicy
    key = "global" if scope == "global" else f"character:{actor.id}"
    db.add(ActivityEnginePolicy(scope_key=key, engine="current", version=1,
        world_id=actor.world_id if scope == "character" else None,
        world_character_id=actor.id if scope == "character" else None,
        updated_at=datetime.now(UTC)))
    db.flush()


def _restored_run(db, actor, activity_id, *, engine="current", version=1):
    from app.domains.world_characters.activity_models import ActivityGraphRun
    row = ActivityGraphRun(activity_id=activity_id, world_id=actor.world_id,
        world_character_id=actor.id, engine=engine, contract_version=version,
        status="completed", stage="Finalize", started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC), result={"historical_receipts": ["existing"]})
    db.add(row)
    db.flush()
    return row


@pytest.fixture(autouse=True)
def _legacy_approved_preparation(monkeypatch):
    """Keep the imported approved-pair fixture in its preserved preparation mode."""
    from app.config import settings

    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)


def test_state_receipts_cas_time_and_duplicate_experience():
    with Session(_engine(), expire_on_commit=False) as db:
        _, actor, _ = _approved(db)
        now = datetime.now(UTC)
        args = dict(world_id=actor.world_id, actor_id=actor.id, activity_id="run", judged_at=now,
                    source_keys=["source1"], valid_source_keys={"source1"})
        assert not read_state(db, world_id=actor.world_id, actor_id=actor.id)["known"]
        proposal = StateUpdate(mood="hopeful", mood_intensity=35, state_note="Ready to try again")
        assert settle_state(db, **args, decision_key="d1", expected_version=0, proposal=proposal) == "updated"
        db.commit()
        assert settle_state(db, **args, decision_key="d1", expected_version=0, proposal=proposal) == "updated"
        assert settle_state(db, **args, decision_key="d2", expected_version=1, proposal=proposal) == "already_interpreted"
        args.update(source_keys=["source2"], valid_source_keys={"source2"}, judged_at=now + timedelta(hours=2))
        assert settle_state(db, **args, decision_key="d3", expected_version=0, proposal=proposal) == "conflict_not_applied"
        assert settle_state(db, **args, decision_key="d4", expected_version=1, proposal=None) == "kept"
        db.commit()
        state = read_state(db, world_id=actor.world_id, actor_id=actor.id)
        assert state["version"] == 2
        assert state["changed_at"] == now.isoformat()
        assert state["confirmed_at"] == (now + timedelta(hours=2)).isoformat()
        assert state["mood"] == "hopeful"
        with pytest.raises(ValueError, match="scope_invalid"):
            read_state(db, world_id="other", actor_id=actor.id)


def test_policy_inheritance_and_claim_frozen_across_global_transition():
    with Session(_engine(), expire_on_commit=False) as db:
        _, actor, _ = _approved(db)
        initialize_created_world_character(
            db, character=db.get(Character, actor.character_id), world_character=actor,
        )
        assert resolve_engine(db, actor) == {"engine": "personalized_graph_v2", "source": "default", "version": 0}
        _restored_policy(db, actor, scope="global")
        first = _restored_run(db, actor, "first")
        with pytest.raises(ValueError, match="engine_invalid"):
            set_engine(db, engine="current", expected_version=1)
        with pytest.raises(ValueError, match="legacy_engine_transition_required"):
            bind_run(db, actor=actor, activity_id="not_admitted")
        with pytest.raises(ValueError, match="legacy_engine_transition_required"):
            set_engine(db, engine="personalized_graph_v2", expected_version=1)
        # The caller's real settlement/readiness boundary is covered by the
        # integration retirement suite; this test keeps policy CAS ownership.
        set_engine(db, engine="personalized_graph_v2", expected_version=1, settled_current=True)
        assert bind_run(db, actor=actor, activity_id="first").engine == first.engine == "current"
        assert bind_run(db, actor=actor, activity_id="second").engine == "personalized_graph_v2"
        _restored_policy(db, actor, scope="character")
        assert resolve_engine(db, actor)["source"] == "character"
        assert bind_run(db, actor=actor, activity_id="second").engine == "personalized_graph_v2"
        set_engine(db, engine=None, expected_version=1, world_id=actor.world_id, actor_id=actor.id)
        assert resolve_engine(db, actor)["engine"] == "personalized_graph_v2"
        assert first.result == {"historical_receipts": ["existing"]}


def test_world_and_character_overrides_preserve_explicit_v1_after_default_switch():
    with Session(_engine(), expire_on_commit=False) as db:
        _, actor, _ = _approved(db)
        _restored_policy(db, actor, scope="global")
        set_engine(db, engine="personalized_graph_v2", expected_version=0, world_id=actor.world_id)
        assert resolve_engine(db, actor)["source"] == "world"
        _restored_policy(db, actor, scope="character")
        assert resolve_engine(db, actor)["engine"] == "current"
        with pytest.raises(ValueError, match="legacy_engine_transition_required"):
            bind_run(db, actor=actor, activity_id="blocked_current")
        set_engine(db, engine=None, expected_version=1, world_id=actor.world_id, actor_id=actor.id)
        assert resolve_engine(db, actor)["source"] == "world"
        set_engine(db, engine=None, expected_version=1, world_id=actor.world_id)
        assert resolve_engine(db, actor)["engine"] == "current"
        set_engine(db, engine=None, expected_version=1)
        assert resolve_engine(db, actor) == {"engine": "personalized_graph_v2", "source": "default", "version": 0}


def test_contract_version_transition_and_rollback_do_not_rebind_existing_runs(monkeypatch):
    from app.domains.world_characters.service import activity_engines
    with Session(_engine(), expire_on_commit=False) as db:
        _, actor, _ = _approved(db)
        initialize_created_world_character(
            db, character=db.get(Character, actor.character_id), world_character=actor,
        )
        assert activity_engines.CONTRACT_VERSION == 2
        _restored_run(db, actor, "old", engine="personalized_graph_v2")
        assert bind_run(db, actor=actor, activity_id="old").contract_version == 1
        assert bind_run(db, actor=actor, activity_id="new").contract_version == 2
        assert bind_run(db, actor=actor, activity_id="old").contract_version == 1
        assert bind_run(db, actor=actor, activity_id="new").contract_version == 2
        _restored_run(db, actor, "rollback", engine="personalized_graph_v2")
        assert bind_run(db, actor=actor, activity_id="rollback").contract_version == 1
        _restored_run(db, actor, "legacy")
        assert bind_run(db, actor=actor, activity_id="legacy").contract_version == 1
        with pytest.raises(ValueError, match="engine_invalid"):
            set_engine(db, engine="current", expected_version=0)
        unsupported = bind_run(db, actor=actor, activity_id="unknown")
        unsupported.contract_version = 99
        with pytest.raises(ValueError, match="scope_or_version_invalid"):
            bind_run(db, actor=actor, activity_id="unknown")
