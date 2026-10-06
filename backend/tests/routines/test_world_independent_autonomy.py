"""World saved intent, admission and frozen inputs on task-owned file SQLite."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.characters.models import Character
from app.domains.identity.models import LlmCredential
from app.domains.identity.service.environment import lock_environment_admission
from app.domains.routines.models import AgentActivitySetting, AgentRun, AgentSlot
from app.domains.routines.service import runs, slot_assignments, slot_leases
from app.runtime.world_configuration.effective_values import character_for_input, setting_for_input
from app.domains.routines.exceptions import ActivityRuntimeValidationError, ActivityProfileRequiredError, RunNowSoonScheduledError
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.worlds.models import World, WorldMembership
from app.domains.world_characters.schemas.management import ExpectedWorldRevision, WorldCharacterSettingsPatch
from app.runtime.characters.management import build_manual_activity_workflows
from app.runtime.resident.context import LangGraphResidentContext
from app.runtime.resident import slots
from app.runtime.routines.activity_policy import build_activity_policy
from app.runtime.routines.configuration_reads import capture_activity_input, read_autonomy_enabled, read_effective_setting
from app.runtime.routines.world_autonomy import reconcile_world_autonomy as _reconcile_world_autonomy
from app.runtime.resident.autonomy_composition import build_autonomy_admission_references
from app.runtime.world_characters.management import management_service
from world_configuration_fixture_support import seed_configuration_fixture, fixture_owner

NOW = datetime(2026, 10, 5, 16, tzinfo=UTC)


def reconcile_world_autonomy(db):
    return _reconcile_world_autonomy(db, workflows=build_autonomy_admission_references())


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OPENCLAW_AGENT_IDS", "world-slot-a,world-slot-b")
    monkeypatch.setattr(settings, "SERVER_LLM_AUTONOMY_MAX_ACTIVE_AGENTS", 2)
    monkeypatch.setattr(settings, "WORLD_AUTONOMY_MAX_ACTIVE_CHARACTERS", 2)
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    result = seed_configuration_fixture(tmp_path / "world-autonomy.sqlite")
    with Session(result) as db:
        for suffix in ("a", "b"):
            row = db.get(WorldCharacterConfiguration, f"config-role-{suffix}")
            row.settings = {**row.settings, "active_hours_start": "09:00", "active_hours_end": "02:00",
                "generation_model": "gemini-3.1-flash-lite", "personality": f"World {suffix} persona"}
        db.commit()
    yield result
    result.dispose()


def intent(db, suffix, enabled):
    role = db.get(WorldCharacter, f"config-role-{suffix}")
    return management_service(db).set_autonomy(world_id=role.world_id, world_character_id=role.id,
        user=fixture_owner(db), data=ExpectedWorldRevision(expected_revision=role.version), enabled=enabled)


def due(db, suffix):
    slot = db.scalar(select(AgentSlot).where(AgentSlot.assigned_character_id == f"config-actor-{suffix}"))
    slot.next_tick_at = NOW - timedelta(minutes=1)
    db.commit()
    return slot


def test_a_b_saved_on_use_existing_slots_and_a_off_preserves_b(engine):
    with Session(engine, expire_on_commit=False) as db:
        assert intent(db, "a", True).summary.enabled == 1
        assert intent(db, "b", True).summary.enabled == 1
        assert reconcile_world_autonomy(db) == 2
        a, b = due(db, "a"), due(db, "b")
        assert a.agent_id != b.agent_id
        b_before = (b.assigned_character_id, b.status, b.next_tick_at, b.locked_by_run_id, b.lease_expires_at)
        assert all(not row.auto_enabled for row in db.scalars(select(AgentActivitySetting)))
        assert intent(db, "a", False).summary.enabled == 0
        assert reconcile_world_autonomy(db) == 1
        assert a.assigned_character_id is None
        assert b_before == (b.assigned_character_id, b.status, b.next_tick_at, b.locked_by_run_id, b.lease_expires_at)
        claimed = slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=120)
        assert [row.assigned_character_id for row in claimed] == ["config-actor-b"]
        assert claimed[0].admission_metadata["_world_configuration"]["world_id"] == "config-world-b"
        assert db.get(WorldCharacter, "config-role-b").autonomous_enabled
        assert db.get(CharacterActiveWorld, "config-actor-a").world_character_id == "config-role-a"
        assert db.get(CharacterActiveWorld, "config-actor-b").world_character_id == "config-role-b"


def test_saved_on_retained_when_pool_capacity_full_and_retry_uses_same_pool(engine, monkeypatch):
    monkeypatch.setattr(settings, "SERVER_LLM_AUTONOMY_MAX_ACTIVE_AGENTS", 1)
    with Session(engine) as db:
        intent(db, "a", True)
        intent(db, "b", True)
        assert reconcile_world_autonomy(db) == 1
        assert reconcile_world_autonomy(db) == 0
        assert all(db.get(WorldCharacter, f"config-role-{s}").autonomous_enabled for s in ("a", "b"))
        assigned = list(db.scalars(select(AgentSlot).where(AgentSlot.assigned_character_id.is_not(None))))
        assert len(assigned) == 1
        first = "a" if assigned[0].assigned_character_id.endswith("a") else "b"
        other = "b" if first == "a" else "a"
        intent(db, first, False)
        assert reconcile_world_autonomy(db) == 2
        assert db.scalar(select(AgentSlot.assigned_character_id).where(AgentSlot.assigned_character_id.is_not(None))) == f"config-actor-{other}"


def test_unsuccessful_slot_assignment_preserves_callers_world_transaction(engine):
    with Session(engine) as db:
        lock_environment_admission(db)
        role = db.get(WorldCharacter, "config-role-a")
        role.autonomous_enabled = True
        with db.begin_nested():
            assert slots.assign_resident_slot(db, agent_ids=["unavailable-actor-slot"], user_id="fixture-owner",
                character_id="missing-world-actor", credential_id="config-credential-a", heartbeat_interval_seconds=1800,
                next_tick_at=NOW, commit=False) is None
        # A rejected pool attempt must leave the saved World intent and its lock
        # in the caller's transaction, rather than roll back unrelated work.
        assert role.autonomous_enabled
        db.commit()
    with Session(engine) as db:
        assert db.get(WorldCharacter, "config-role-a").autonomous_enabled
        assert db.scalar(select(AgentSlot.assigned_character_id).where(AgentSlot.agent_id == "unavailable-actor-slot")) is None


def test_claim_freezes_world_persona_model_policy_and_revision_across_edit_and_off(engine):
    with Session(engine, expire_on_commit=False) as db:
        intent(db, "a", True)
        intent(db, "b", True)
        reconcile_world_autonomy(db)
        a, b = due(db, "a"), due(db, "b")
        claimed = slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=180)
        assert {row.assigned_character_id for row in claimed} == {"config-actor-a", "config-actor-b"}
        original = deepcopy(a.admission_metadata)
        b_original = deepcopy(b.admission_metadata)
        a_lease = (a.locked_by_run_id, a.lease_expires_at)
        role = db.get(WorldCharacter, "config-role-a")
        management_service(db).patch_settings(world_id=role.world_id, world_character_id=role.id,
            user=fixture_owner(db), data=WorldCharacterSettingsPatch(expected_revision=role.version,
                settings={"personality": "Edited after admission", "generation_model": "gemini-3.5-flash-lite",
                    "max_posts_per_day": 0}))
        intent(db, "a", False)
        assert reconcile_world_autonomy(db) == 0
        assert original == a.admission_metadata and b_original == b.admission_metadata
        assert a_lease == (a.locked_by_run_id, a.lease_expires_at)
        run = runs.create_agent_run(db, run_id="frozen-world-run", user_id="fixture-owner",
            character_id="config-actor-a", post_id=None, credential_id="config-credential-a",
            agent_id=a.agent_id, session_key="agent:world:resident-tick:frozen", input_snapshot=a.admission_metadata)
        view = character_for_input(db.get(Character, run.character_id), run.input_snapshot)
        policy = build_activity_policy(db, character_id=run.character_id, now=NOW,
            frozen_input=True, input_snapshot=run.input_snapshot)
        assert view.personality == "World a persona" and "post" in policy.allowed_actions
        assert db.get(Character, run.character_id).personality == "Original persona"
        ctx = LangGraphResidentContext(db=db, run_id=run.id, user_id=run.user_id, agent_id=a.agent_id,
            session_key=run.session_key, character=view, credential=db.get(LlmCredential, run.credential_id),
            state=None, activity_policy=policy, selected_post_id=None, run_started_at=NOW, input_snapshot=run.input_snapshot)
        assert ctx.generation_model == "gemini-3.1-flash-lite"
        assert run.input_snapshot["_world_configuration"]["revision"] < role.version
        runs.mark_agent_run_finished(db, run.id, "completed")
        slot_leases.complete_resident_slot_run(db, agent_id=a.agent_id, run_id=a.locked_by_run_id,
            heartbeat_interval_seconds=1800)
        due(db, "a")
        assert slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=120) == []


def test_world_default_generation_model_and_thinking_captured_once(engine):
    with Session(engine, expire_on_commit=False) as db:
        stored = db.get(WorldCharacterConfiguration, "config-role-a")
        stored.settings = {**stored.settings, "generation_model": None}
        credential = db.get(LlmCredential, "config-credential-a")
        credential.thinking_level = "medium"
        db.commit()
        metadata = capture_activity_input(db, character_id="config-actor-a")
        credential.model, credential.thinking_level = "gemini-3.5-flash-lite", "high"
        db.commit()
        view = character_for_input(db.get(Character, "config-actor-a"), metadata)
        policy = build_activity_policy(db, character_id=view.id, now=NOW, frozen_input=True, input_snapshot=metadata)
        ctx = LangGraphResidentContext(db=db, run_id="not-requeried", user_id="fixture-owner", agent_id="test",
            session_key="test", character=view, credential=credential, state=None,
            activity_policy=policy, selected_post_id=None, run_started_at=NOW, input_snapshot=metadata)
        assert ctx.generation_model == "gemini-3.1-flash-lite" and ctx.generation_thinking_level == "medium"


def test_world_active_hours_blocks_new_claim_preserving_saved_on(engine):
    with Session(engine) as db:
        intent(db, "a", True)
        reconcile_world_autonomy(db)
        a = due(db, "a")
        stored = db.get(WorldCharacterConfiguration, "config-role-a")
        stored.settings = {**stored.settings, "active_hours_start": "02:00", "active_hours_end": "03:00"}
        db.commit()
        assert slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=60) == []
        assert db.get(WorldCharacter, "config-role-a").autonomous_enabled
        assert a.status != "running" and a.admission_metadata is None
        assert a.last_error == "world_active_hours_waiting"
        assert a.next_tick_at.replace(tzinfo=UTC) > NOW


@pytest.mark.parametrize("status,readiness", [("draft", "not_ready"), ("published", "not_ready"), ("published", "stale")])
def test_saved_world_policy_is_readable_before_publish_but_automatic_and_manual_admission_are_rejected(engine, status, readiness):
    from app.domains.routines.service.manual_activity import run_agent_now
    with Session(engine) as db:
        intent(db, "a", True)
        assert reconcile_world_autonomy(db) == 1
        automatic_slot = due(db, "a")
        for suffix in ("a", "b"):
            world = db.get(World, f"config-world-{suffix}")
            world.status, world.readiness_status = status, readiness
            configuration = db.get(WorldCharacterConfiguration, f"config-role-{suffix}")
            configuration.settings = {**configuration.settings, "activity_interval_minutes": 17, "max_posts_per_day": 3}
        db.commit()
        common = db.get(AgentActivitySetting, "config-actor-a")
        saved = (common.activity_interval_minutes, common.max_posts_per_day, common.auto_enabled)
        effective = read_effective_setting(db, character_id=common.character_id, setting=common)
        assert effective.activity_interval_minutes == 17 and effective.max_posts_per_day == 3
        assert effective.auto_enabled and not read_autonomy_enabled(db, character_id=common.character_id, setting=common)
        assert saved == (common.activity_interval_minutes, common.max_posts_per_day, common.auto_enabled)
        assert db.get(World, "config-world-a").status == status
        with pytest.raises(ActivityRuntimeValidationError, match="world_scope_not_ready"):
            capture_activity_input(db, character_id=common.character_id)
        assert slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=120) == []
        assert automatic_slot.status != "running" and automatic_slot.locked_by_run_id is None
        assert automatic_slot.admission_metadata is None and automatic_slot.last_error == "world_scope_not_ready"
        # Manual admission still uses the real readiness and temporary-lease paths.
        with pytest.raises(ActivityProfileRequiredError):
            asyncio.run(run_agent_now(db, fixture_owner(db), "config-actor-b", scoped_world_id="config-world-b",
                workflows=build_manual_activity_workflows()))
        with pytest.raises(ActivityRuntimeValidationError, match="world_scope_not_ready"):
            slots.claim_temporary_resident_slot_assignment(db, agent_ids=settings.openclaw_agent_ids,
                user_id="fixture-owner", character_id="config-actor-b", credential_id="config-credential-b",
                heartbeat_interval_seconds=1800, lease_seconds=90)
        db.rollback()
        assert all(slot.status != "running" and slot.locked_by_run_id is None and slot.admission_metadata is None
            for slot in db.scalars(select(AgentSlot)))
        assert db.query(AgentRun).count() == 0
        assert db.get(WorldCharacter, "config-role-a").autonomous_enabled
        assert not db.get(WorldCharacter, "config-role-b").autonomous_enabled


@pytest.mark.parametrize("invalid_scope,reason", [
    ("inactive_role", "world_character_inactive"), ("left_membership", "world_scope_not_ready"),
    ("missing_binding", "world_character_binding_invalid"), ("missing_configuration", "world_configuration_missing"),
])
def test_settings_read_retains_role_membership_binding_and_configuration_guards(engine, invalid_scope, reason):
    with Session(engine) as db:
        if invalid_scope == "inactive_role":
            db.get(WorldCharacter, "config-role-a").status = "inactive"
        elif invalid_scope == "left_membership":
            db.get(WorldMembership, "config-member-a").status = "left"
        elif invalid_scope == "missing_binding":
            db.delete(db.get(CharacterActiveWorld, "config-actor-a"))
        else:
            db.delete(db.get(WorldCharacterConfiguration, "config-role-a"))
        db.commit()
        setting = db.get(AgentActivitySetting, "config-actor-a")
        with pytest.raises(ActivityRuntimeValidationError, match=reason):
            read_effective_setting(db, character_id=setting.character_id, setting=setting)
        assert not read_autonomy_enabled(db, character_id=setting.character_id, setting=setting)
        assert db.query(AgentRun).count() == 0


def test_duplicate_actor_and_single_flight_use_existing_lease_checks(engine):
    with Session(engine) as db:
        for suffix in ("a", "b"):
            intent(db, suffix, True)
        reconcile_world_autonomy(db)
        due(db, "a")
        due(db, "b")
        first = slots.claim_resident_slot_assignment(db, user_id="fixture-owner", character_id="config-actor-a", lease_seconds=300)
        assert first is not None
        before = (first.locked_by_run_id, first.lease_expires_at, deepcopy(first.admission_metadata))
        assert slots.claim_resident_slot_assignment(db, user_id="fixture-owner", character_id="config-actor-a", lease_seconds=300) is None
        assert slots.claim_due_resident_slots(db, now=datetime.now(UTC), max_count=2, lease_seconds=300, single_flight=True) == []
        assert before == (first.locked_by_run_id, first.lease_expires_at, first.admission_metadata)


@pytest.mark.parametrize("change_first", [False, True])
def test_off_and_automatic_admission_serialize_through_same_identity_lock(engine, change_first):
    with Session(engine) as db:
        intent(db, "a", True)
        reconcile_world_autonomy(db)
        due(db, "a")
    started, release = Event(), Event()
    def second_operation():
        started.set()
        with Session(engine) as db:
            if change_first:
                return slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=120)
            intent(db, "a", False)
            return None
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as db:
            lock_environment_admission(db, "fixture-owner")
            future = pool.submit(second_operation)
            assert started.wait(3) and not future.done()
            if change_first:
                intent(db, "a", False)
            else:
                accepted = slots.claim_due_resident_slots(db, now=NOW, max_count=2, lease_seconds=120)
                assert len(accepted) == 1
                original = deepcopy(accepted[0].admission_metadata)
            result = future.result(timeout=10)
        with Session(engine) as db:
            role = db.get(WorldCharacter, "config-role-a")
            assert not role.autonomous_enabled
            slot = db.scalar(select(AgentSlot).where(AgentSlot.assigned_character_id == role.character_id))
            if change_first:
                assert result == [] and slot.status != "running"
            else:
                assert slot.status == "running" and slot.admission_metadata == original


@pytest.mark.parametrize("edit_first", [False, True])
def test_settings_revision_and_admission_are_ordered_on_real_sessions(engine, edit_first):
    with Session(engine) as db:
        intent(db, "a", True)
        reconcile_world_autonomy(db)
        due(db, "a")
    started = Event()
    def edit(db):
        role = db.get(WorldCharacter, "config-role-a")
        management_service(db).patch_settings(world_id=role.world_id, world_character_id=role.id,
            user=fixture_owner(db), data=WorldCharacterSettingsPatch(expected_revision=role.version,
                settings={"personality": "New revision persona"}))
    def second():
        started.set()
        with Session(engine) as db:
            if edit_first:
                return slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)[0].admission_metadata
            edit(db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as db:
            lock_environment_admission(db, "fixture-owner")
            future = pool.submit(second)
            assert started.wait(3) and not future.done()
            if edit_first:
                edit(db)
                accepted = future.result(timeout=10)
            else:
                accepted = slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)[0].admission_metadata
                future.result(timeout=10)
        assert accepted["_world_configuration"]["settings"]["personality"] == (
            "New revision persona" if edit_first else "World a persona")


@pytest.mark.parametrize("revoke_first", [False, True])
def test_membership_revocation_and_admission_are_ordered_without_releasing_an_accepted_lease(engine, revoke_first):
    with Session(engine) as db:
        intent(db, "a", True)
        reconcile_world_autonomy(db)
        due(db, "a")
    started = Event()
    def revoke(db):
        membership = db.get(WorldMembership, "config-member-a")
        membership.status = "left"
        membership.left_at = datetime.now(UTC)
        db.commit()
    def second():
        started.set()
        with Session(engine) as db:
            if revoke_first:
                return slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)
            lock_environment_admission(db, "fixture-owner")
            revoke(db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as db:
            lock_environment_admission(db, "fixture-owner")
            future = pool.submit(second)
            assert started.wait(3) and not future.done()
            if revoke_first:
                revoke(db)
                assert future.result(timeout=10) == []
            else:
                accepted = slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)
                assert len(accepted) == 1
                snapshot = deepcopy(accepted[0].admission_metadata)
                lease = (accepted[0].locked_by_run_id, accepted[0].lease_expires_at)
                future.result(timeout=10)
    with Session(engine) as db:
        role = db.get(WorldCharacter, "config-role-a")
        assert role.autonomous_enabled
        assert db.get(WorldMembership, "config-member-a").status == "left"
        assert db.get(WorldMembership, "config-member-b").status == "active"
        slot = db.scalar(select(AgentSlot).where(AgentSlot.assigned_character_id == role.character_id))
        if revoke_first:
            assert slot.status != "running" and slot.locked_by_run_id is None
            assert slot.admission_metadata is None and slot.last_error == "world_scope_not_ready"
        else:
            assert slot.status == "running" and slot.admission_metadata == snapshot
            assert (slot.locked_by_run_id, slot.lease_expires_at) == lease
            assert snapshot["_world_configuration"]["world_id"] == "config-world-a"


def test_missing_world_configuration_is_rejected_before_manual_lease(engine):
    with Session(engine) as db:
        db.delete(db.get(WorldCharacterConfiguration, "config-role-b"))
        db.commit()
        with pytest.raises(ActivityRuntimeValidationError, match="world_configuration_missing"):
            slots.claim_temporary_resident_slot_assignment(db, agent_ids=settings.openclaw_agent_ids,
                user_id="fixture-owner", character_id="config-actor-b", credential_id="config-credential-b",
                heartbeat_interval_seconds=1800, lease_seconds=90)
        db.rollback()
        assert all(row.status != "running" for row in db.scalars(select(AgentSlot)))


def test_scoped_b_run_now_while_off_uses_b_snapshot_and_keeps_a_intent(engine, monkeypatch):
    from app.domains.routines.service.manual_activity import run_agent_now
    with Session(engine, expire_on_commit=False) as db:
        intent(db, "a", True)
        a_before = deepcopy(db.get(WorldCharacterConfiguration, "config-role-a").settings)
        workflows = build_manual_activity_workflows()
        captured = []
        async def controlled_worker(session, **args):
            slot = session.get(AgentSlot, args["agent_id"])
            captured.append(deepcopy(slot.admission_metadata))
            run = runs.create_agent_run(session, run_id="b-manual-fake", user_id=args["user_id"],
                character_id=args["character_id"], post_id=None, credential_id=args["credential_id"],
                agent_id=slot.agent_id, session_key="agent:b:resident-manual:fixture", input_snapshot=slot.admission_metadata)
            runs.mark_agent_run_finished(session, run.id, "completed", gateway_result={"fake": True})
            slot_leases.complete_resident_slot_run(session, agent_id=slot.agent_id, run_id=slot.locked_by_run_id,
                heartbeat_interval_seconds=1800)
            return SimpleNamespace(id=run.id, status="completed")
        result = asyncio.run(run_agent_now(db, fixture_owner(db), "config-actor-b", scoped_world_id="config-world-b",
            workflows=replace(workflows, run_temporary_slot=controlled_worker)))
        assert result.status == "completed" and len(captured) == 1
        assert captured[0]["_world_configuration"]["world_id"] == "config-world-b"
        assert captured[0]["_world_configuration"]["settings"]["personality"] == "World b persona"
        assert not db.get(WorldCharacter, "config-role-b").autonomous_enabled
        assert db.get(WorldCharacter, "config-role-a").autonomous_enabled
        assert a_before == db.get(WorldCharacterConfiguration, "config-role-a").settings
        assert all(row.assigned_character_id is None for row in db.scalars(select(AgentSlot)))
        assert db.get(AgentRun, "b-manual-fake").input_snapshot == captured[0]


def test_manual_imminent_guard_reads_world_on_even_when_global_flag_off(engine):
    from app.domains.routines.service.manual_activity import run_agent_now
    with Session(engine) as db:
        intent(db, "a", True)
        reconcile_world_autonomy(db)
        slot = db.scalar(select(AgentSlot).where(AgentSlot.assigned_character_id == "config-actor-a"))
        slot.next_tick_at = datetime.now(UTC) + timedelta(seconds=10)
        db.commit()
        assert not db.get(AgentActivitySetting, "config-actor-a").auto_enabled
        with pytest.raises(RunNowSoonScheduledError):
            asyncio.run(run_agent_now(db, fixture_owner(db), "config-actor-a", scoped_world_id="config-world-a",
                workflows=build_manual_activity_workflows()))
        assert db.query(AgentRun).count() == 0
