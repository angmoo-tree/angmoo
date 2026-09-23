from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.domains.world_characters.service.activity_state import read_state, settle_state
from app.domains.world_characters.service.activity_engines import bind_run, resolve_engine, set_engine
from world_characters.test_persona_continuity import _approved, _engine


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
        assert resolve_engine(db, actor) == {"engine": "personalized_graph_v2", "source": "default", "version": 0}
        set_engine(db, engine="current", expected_version=0)
        first = bind_run(db, actor=actor, activity_id="first")
        set_engine(db, engine="personalized_graph_v2", expected_version=1)
        assert bind_run(db, actor=actor, activity_id="first").engine == first.engine == "current"
        assert bind_run(db, actor=actor, activity_id="second").engine == "personalized_graph_v2"
        set_engine(db, engine="current", expected_version=0, world_id=actor.world_id, actor_id=actor.id)
        assert resolve_engine(db, actor)["source"] == "character"
        assert bind_run(db, actor=actor, activity_id="second").engine == "personalized_graph_v2"
        set_engine(db, engine=None, expected_version=1, world_id=actor.world_id, actor_id=actor.id)
        assert resolve_engine(db, actor)["engine"] == "personalized_graph_v2"


def test_world_and_character_overrides_preserve_explicit_v1_after_default_switch():
    with Session(_engine(), expire_on_commit=False) as db:
        _, actor, _ = _approved(db)
        set_engine(db, engine="current", expected_version=0)
        set_engine(db, engine="personalized_graph_v2", expected_version=0, world_id=actor.world_id)
        assert resolve_engine(db, actor)["source"] == "world"
        set_engine(db, engine="current", expected_version=0, world_id=actor.world_id, actor_id=actor.id)
        assert resolve_engine(db, actor)["engine"] == "current"
        set_engine(db, engine=None, expected_version=1, world_id=actor.world_id, actor_id=actor.id)
        assert resolve_engine(db, actor)["source"] == "world"
        set_engine(db, engine=None, expected_version=1, world_id=actor.world_id)
        assert resolve_engine(db, actor)["engine"] == "current"
        set_engine(db, engine=None, expected_version=1)
        assert resolve_engine(db, actor) == {"engine": "personalized_graph_v2", "source": "default", "version": 0}
