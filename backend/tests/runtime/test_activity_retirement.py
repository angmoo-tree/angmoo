"""Exercise retirement and shared overrides against actual canonical rows."""
import asyncio
from datetime import UTC, datetime, timedelta
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines.models import AgentRun, AgentSlot, AgentPublicActionExecution
from app.domains.world_characters.activity_models import ActivityGraphRun, ActivityEnginePolicy
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run, set_engine
from app.domains.world_characters.schemas.activity_state import EngineSelection
from app.runtime.autonomous_activity.retirement import transition_uow
from tests.social.test_feed_reaction_intent import _engine, _seed

NOW = datetime(2026, 10, 3, tzinfo=UTC)
pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture
def canonical():
    engine = _engine()
    with Session(engine) as db:
        _seed(db, with_candidate=False)
        db.commit()
    yield engine
    engine.dispose()


def old_activity(db, *, engine="current", version=1, payload=None, status="interrupted"):
    actor = db.scalar(select(WorldCharacter).where(WorldCharacter.character_id == "actor"))
    # Fixture IDs are owner-specific; bind ownership through the actual actor.
    if actor is None:
        actor = db.get(WorldCharacter, "world-character-actor")
    from app.domains.characters.models import Character
    owner_id = db.get(Character, actor.character_id).owner_id
    run = AgentRun(id="old-run", user_id=owner_id, character_id=actor.character_id,
        agent_id="old-slot", session_key="old-sns", status="running", gateway_result={"usage": {"calls": 2}})
    row = ActivityGraphRun(activity_id=run.id, world_id=actor.world_id, world_character_id=actor.id,
        engine=engine, contract_version=version, status=status, stage="RoutineActivityGraph",
        started_at=NOW-timedelta(days=2), result=payload)
    actor_id = actor.id
    db.add_all([run, row]); db.commit()
    return actor_id


@pytest.mark.parametrize("engine,version", [("current", 1), ("personalized_graph_v2", 1)])
def test_old_partial_success_is_abandoned_without_rewriting_effects_or_policies(canonical, engine, version):
    payload = {"paths": {"inbox": {"status": "completed", "public_action_count": 1}},
        "recovery_reservations": ["FeedActionPlanner:json"], "routine_policy": {"old": True}}
    with Session(canonical) as db:
        actor_id = old_activity(db, engine=engine, version=version, payload=deepcopy(payload))
        result = transition_uow(db, actor_id=actor_id, now=NOW)
        assert result.abandoned_count == 1 and result.state == "ready"
        row = db.get(ActivityGraphRun, "old-run")
        assert row.status == "abandoned" and row.engine == engine and row.contract_version == version
        assert row.finished_at is not None and row.result["reason"] == "legacy_sns_abandoned"
        for key, value in payload.items():
            assert row.result[key] == value
        assert "checkpoint_retention" not in row.result
        run = db.get(AgentRun, "old-run")
        assert run.status == "aborted" and run.gateway_result["usage"] == {"calls": 2}
        db.commit()
        assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 0


def test_old_null_result_and_completed_history_are_readable(canonical):
    with Session(canonical) as db:
        actor_id = old_activity(db, payload=None)
        assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 1
        original = deepcopy(db.get(ActivityGraphRun, "old-run").result)
        db.commit()
        assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 0
        assert db.get(ActivityGraphRun, "old-run").result == original


@pytest.mark.parametrize("hold", ["lease", "pending_effect"])
def test_live_owner_or_unconfirmed_effect_blocks_only_actor(canonical, hold):
    with Session(canonical) as db:
        actor_id = old_activity(db, payload={"reserved": True})
        actor = db.get(WorldCharacter, actor_id)
        if hold == "lease":
            db.add(AgentSlot(agent_id="old-slot", status="running", assigned_character_id=actor.character_id,
                assigned_user_id="user-owner", locked_by_run_id="old-run", lease_expires_at=NOW+timedelta(minutes=1)))
        else:
            db.add(AgentPublicActionExecution(run_id="old-run", character_id=actor.character_id,
                signature="uncertain-effect", scope="inbox", action_type="comment", status="pending"))
        db.commit()
        outcome = transition_uow(db, actor_id=actor_id, now=NOW)
        assert outcome.state == "pending_settlement"
        assert db.get(ActivityGraphRun, "old-run").status == "interrupted"
        assert db.get(AgentRun, "old-run").status == "running"


def test_current_override_changes_only_after_readiness_and_keeps_autonomy(canonical):
    with Session(canonical) as db:
        actor_id = old_activity(db, payload={})
        actor = db.get(WorldCharacter, actor_id)
        initial = (actor.autonomous_enabled, actor.version)
        db.add(ActivityEnginePolicy(scope_key=f"character:{actor.id}", world_id=actor.world_id,
            world_character_id=actor.id, engine="current", version=4, updated_at=NOW))
        db.commit()
        outcome = transition_uow(db, actor_id=actor_id, now=NOW, readiness=lambda *a, **k: "legacy_v2_preparation_not_ready")
        assert outcome.state == "needs_preparation" and outcome.abandoned_count == 1
        policy = db.get(ActivityEnginePolicy, f"character:{actor_id}")
        assert (policy.engine, policy.version) == ("current", 4)
        db.commit()
        outcome = transition_uow(db, actor_id=actor_id, now=NOW, readiness=lambda *a, **k: None)
        assert outcome.converted_count == 1
        db.expire_all()
        assert (policy.engine, policy.version) == ("personalized_graph_v2", 5)
        actor = db.get(WorldCharacter, actor_id)
        assert (actor.autonomous_enabled, actor.version) == initial
        db.commit()
        assert transition_uow(db, actor_id=actor_id, now=NOW).converted_count == 0


def test_new_writes_reject_current_and_null_inheritance_is_unchanged(canonical):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EngineSelection(engine="current", expected_version=0)
    with Session(canonical) as db:
        with pytest.raises(ValueError, match="engine_invalid"):
            set_engine(db, engine="current", expected_version=0)
        actor = db.get(WorldCharacter, "world-character-actor")
        set_engine(db, engine=None, expected_version=0, world_id=actor.world_id, actor_id=actor.id)
        db.commit()
        actor_id = actor.id
        db.commit()
        assert transition_uow(db, actor_id=actor_id, now=NOW).state == "ready"
        assert db.get(ActivityEnginePolicy, f"character:{actor.id}") is None


def test_v2_common_legacy_policy_activity_is_never_retired(canonical):
    with Session(canonical) as db:
        actor_id = old_activity(db, engine="personalized_graph_v2", version=2, payload={})
        assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 0
        assert db.get(ActivityGraphRun, "old-run").status == "interrupted"


def test_direct_current_conversion_cannot_skip_supported_settlement(canonical):
    with Session(canonical) as db:
        actor = db.get(WorldCharacter, "world-character-actor")
        db.add(ActivityEnginePolicy(scope_key=f"character:{actor.id}", world_id=actor.world_id,
            world_character_id=actor.id, engine="current", version=1, updated_at=NOW))
        db.commit()
        with pytest.raises(ValueError, match="legacy_engine_transition_required"):
            set_engine(db, engine="personalized_graph_v2", expected_version=1,
                       world_id=actor.world_id, actor_id=actor.id)
        assert db.get(ActivityEnginePolicy, f"character:{actor.id}").engine == "current"


def test_one_live_actor_does_not_block_other_world_retirement_or_shared_readiness(canonical):
    from app.domains.characters.models import Character
    from app.domains.worlds.models import World, WorldMembership
    from app.runtime.autonomous_activity.retirement import transition_all
    with Session(canonical) as db:
        actor_id = old_activity(db, payload={"partial_success": True})
        actor = db.get(WorldCharacter, actor_id)
        character = db.get(Character, actor.character_id)
        world = db.get(World, actor.world_id)
        db.add(Character(id="second-character", owner_id=character.owner_id, name="Second", handle="second",
                         persona_summary="Synthetic second actor"))
        db.add(World(id="second-world", slug="second-world", name="Independent", owner_user_id=character.owner_id,
                     contract_version=world.contract_version, contract_hash=world.contract_hash,
                     create_idempotency_key="second-world-fixture"))
        db.flush()
        db.add(WorldMembership(id="second-membership", world_id="second-world", user_id=character.owner_id,
                               role="owner", status="active"))
        db.flush()
        db.add(WorldCharacter(id="second-actor", world_id="second-world", character_id="second-character",
            membership_id="second-membership", control_mode="autonomous", status="active", autonomous_enabled=True))
        db.add(AgentRun(id="second-old", user_id=character.owner_id, character_id="second-character",
            agent_id="second-slot", session_key="second-sns", status="interrupted"))
        db.flush()
        db.add(ActivityGraphRun(activity_id="second-old", world_id="second-world", world_character_id="second-actor",
            engine="personalized_graph_v2", contract_version=1, status="interrupted", stage="Feed", started_at=NOW, result={"usage": {"calls": 3}}))
        db.add(AgentSlot(agent_id="old-slot", status="running", assigned_character_id=actor.character_id,
            assigned_user_id=character.owner_id, locked_by_run_id="old-run", lease_expires_at=NOW+timedelta(minutes=1)))
        db.commit()
        outcomes = transition_uow(db, now=NOW)
        assert outcomes[actor_id].state == "pending_settlement"
        assert outcomes["second-actor"].state == "ready" and outcomes["second-actor"].abandoned_count == 1
        assert db.get(ActivityGraphRun, "second-old").status == "abandoned"
        assert db.get(ActivityGraphRun, "second-old").result["usage"] == {"calls": 3}
        assert db.get(ActivityGraphRun, "old-run").status == "interrupted"


def test_shared_current_scope_waits_for_every_inheriting_actor_but_not_specific_v2(canonical):
    from app.domains.characters.models import Character
    from app.domains.world_characters.service.activity_engines import resolve_engine
    with Session(canonical) as db:
        actor_id = old_activity(db, payload={"preserved": True})
        actor = db.get(WorldCharacter, actor_id)
        original = (actor.autonomous_enabled, actor.version)
        for suffix in ("unready", "specific"):
            db.add(Character(id=suffix, owner_id="user-owner", name=suffix, handle=suffix,
                             persona_summary="Synthetic scope fixture"))
            db.flush()
            db.add(WorldCharacter(id=suffix, world_id=actor.world_id, character_id=suffix,
                membership_id=actor.membership_id, control_mode="autonomous", status="active",
                autonomous_enabled=False))
        db.flush()
        db.add(ActivityEnginePolicy(scope_key="global", engine="current", version=3, updated_at=NOW))
        db.add(ActivityEnginePolicy(scope_key="character:specific", engine="personalized_graph_v2",
            world_id=actor.world_id, world_character_id="specific", version=7, updated_at=NOW))
        db.commit()
        checked = []
        def readiness(_db, candidate, **_kwargs):
            checked.append(candidate.id)
            return "legacy_v2_preparation_not_ready" if candidate.id == "unready" else None
        result = transition_uow(db, actor_id=actor_id, now=NOW, readiness=readiness)
        assert result.state == "needs_preparation" and result.abandoned_count == 1
        assert db.get(ActivityGraphRun, "old-run").status == "abandoned"
        assert db.get(ActivityEnginePolicy, "global").engine == "current"
        assert "specific" not in checked
        assert resolve_engine(db, db.get(WorldCharacter, "specific"))["engine"] == "personalized_graph_v2"
        db.commit()
        result = transition_uow(db, actor_id=actor_id, now=NOW, readiness=lambda *a, **k: None)
        assert result.converted_count == 1
        db.expire_all()
        global_policy = db.get(ActivityEnginePolicy, "global")
        assert (global_policy.engine, global_policy.version) == ("personalized_graph_v2", 4)
        assert db.get(ActivityEnginePolicy, "character:specific").version == 7
        assert (db.get(WorldCharacter, actor_id).autonomous_enabled, db.get(WorldCharacter, actor_id).version) == original
        assert db.get(WorldCharacter, "unready").autonomous_enabled is False


def test_policy_revision_conflict_preserves_settlement_and_newer_override(canonical, monkeypatch):
    from app.domains.world_characters.service import activity_engines
    original_set = activity_engines.set_engine
    with Session(canonical) as db:
        actor_id = old_activity(db, payload={"usage": {"calls": 2}})
        actor = db.get(WorldCharacter, actor_id)
        db.add(ActivityEnginePolicy(scope_key=f"character:{actor_id}", world_id=actor.world_id,
            world_character_id=actor_id, engine="current", version=1, updated_at=NOW))
        db.commit()
        def competing_revision(session, **kwargs):
            row = session.get(ActivityEnginePolicy, f"character:{actor_id}")
            row.version = 2
            session.flush()
            return original_set(session, **kwargs)
        monkeypatch.setattr(activity_engines, "set_engine", competing_revision)
        result = transition_uow(db, actor_id=actor_id, now=NOW, readiness=lambda *a, **k: None)
        assert result.state == "pending_conversion" and result.reason == "engine_policy_conflict"
        assert result.abandoned_count == 1 and result.converted_count == 0
        assert db.get(ActivityGraphRun, "old-run").status == "abandoned"
        assert db.get(ActivityGraphRun, "old-run").result["usage"] == {"calls": 2}
        policy = db.get(ActivityEnginePolicy, f"character:{actor_id}")
        assert (policy.engine, policy.version) == ("current", 2)
        db.commit()
        monkeypatch.setattr(activity_engines, "set_engine", original_set)
        assert transition_uow(db, actor_id=actor_id, now=NOW, readiness=lambda *a, **k: None).converted_count == 1


def test_actual_approved_setup_and_day_plan_readiness_controls_current_transition(monkeypatch):
    from app.config import settings
    from app.domains.routines.contracts.plans import PlanScope
    from app.domains.routines.service import daily_preparation as store
    from app.runtime.autonomous_activity.retirement import v2_readiness
    from tests.routines.test_daily_activity_runtime import _engine, _seed
    from tests.routines.test_daily_preparation import output
    from tests.routines.test_ordinary_daily_generation import topics_ready
    from app.domains.social.service.recommendation_topics import mark_new_subject
    from app.domains.worlds.models import WorldRole
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    engine = _engine()
    try:
        with Session(engine) as db:
            world, ready, _ = _seed(db)
            actor = ready.world_character
            actor_id = actor.id
            world.owner_user_id = ready.user.id
            db.add(WorldRole(id="transition-role", world_id=world.id, role_key="student", name="학생"))
            db.add(ActivityEnginePolicy(scope_key=f"character:{actor.id}", world_id=world.id,
                world_character_id=actor.id, engine="current", version=1, updated_at=NOW))
            db.commit()
            assert v2_readiness(db, actor, now=NOW) == "legacy_v2_preparation_not_ready"
            db.commit()
            result = transition_uow(db, actor_id=actor_id, now=NOW)
            assert result.state == "needs_preparation" and result.converted_count == 0
            store.apply_plan(db, scope=PlanScope(world, ready.membership, actor, ready.character),
                output=output(), target_date=NOW.astimezone(ZoneInfo(world.timezone)).date(),
                now=NOW, source_digest="a" * 64, expected_snapshot={})
            mark_new_subject(db, world_id=world.id, world_character_id=actor.id)
            topics_ready(db, world, ready)
            db.commit()
            assert v2_readiness(db, actor, now=NOW) is None
            db.commit()
            result = transition_uow(db, actor_id=actor_id, now=NOW)
            assert result.state == "ready" and result.converted_count == 1
            assert db.get(ActivityEnginePolicy, f"character:{actor_id}").engine == "personalized_graph_v2"
    finally:
        engine.dispose()
