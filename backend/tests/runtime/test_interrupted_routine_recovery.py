"""Recovery cadence and the original frozen draft; no provider network calls."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc, FakeRoutineProvider
from app.config import settings
from app.contracts.activity_cancellation import CancellationReason, RECOVERY_POLICY_KEY, RECOVERY_REVISION
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.routines.models import AgentSlot, AgentRun
from app.domains.routines.service.slot_leases import cancel_resident_run
from app.domains.routines.service.tick_schedule import next_tick_schedule
from app.domains.routines.service.execution.claims import reclaim_frozen_beat
from app.domains.routines.exceptions import ActivityRuntimeConflictError
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.resident.activity_recovery import cancellation_schedule, recovery_due
from app.runtime.routine_posts.sqlalchemy_runtime import prepare_routine_activity, publish_routine_activity
from app.runtime.autonomous_activity.routine_resume import freeze_prepared, restore_prepared


@pytest.fixture
def routine(monkeypatch):
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        now = _utc(datetime(2026, 8, 10, 10, 5))
        ctx = _resident_context(db, fixture, run_id="interrupted-routine", now=now)
        tracker = RunLlmTracker(max_calls=2)
        prepared = prepare_routine_activity(ctx, tracker=tracker)
        assert not isinstance(prepared, dict)
        yield db, fixture, ctx, prepared, tracker
    engine.dispose()


def test_30_minute_cadence_does_not_delay_cancelled_activity_past_26_minute_window(routine):
    db, fixture, ctx, prepared, tracker = routine
    now = ctx.run_started_at
    prepared.context.item.scheduled_end_at = now + timedelta(minutes=26)
    db.add(ActivityGraphRun(activity_id=ctx.run_id, world_id=fixture.world.id,
        world_character_id=fixture.world_character.id, engine="personalized_graph_v2", contract_version=2,
        status="running", stage="routine.Execute", started_at=now,
        result={RECOVERY_POLICY_KEY: RECOVERY_REVISION, "_routine_recovery": {"revision":"routine-recovery.v1", "beat_id": prepared.beat.id}}))
    slot = db.get(AgentSlot, ctx.agent_id)
    if slot is None:
        slot = AgentSlot(agent_id=ctx.agent_id); db.add(slot)
    slot.status = "running"; slot.locked_by_run_id = ctx.run_id
    slot.assigned_user_id = ctx.user_id; slot.assigned_character_id = ctx.character.id
    slot.lease_expires_at = now + timedelta(minutes=10)
    setting = SimpleNamespace(activity_interval_minutes=30, active_hours_start="00:00", active_hours_end="23:59")
    ordinary = next_tick_schedule(setting, character_id=ctx.character.id, now=now, within_active_hours=True)
    assert ordinary.next_tick_at >= now + timedelta(minutes=30)
    slot.next_tick_at = ordinary.next_tick_at
    db.commit()
    cancel_resident_run(db, agent_id=ctx.agent_id, run_id=ctx.run_id, owner_id=ctx.user_id,
        character_id=ctx.character.id, now=now, reason=CancellationReason.HEARTBEAT,
        resolve_schedule=lambda db, slot, current: cancellation_schedule(db, slot, current,
            run_id=ctx.run_id, reason=CancellationReason.HEARTBEAT, heartbeat_interval=1800,
            setting=setting, timezone=ZoneInfo("Asia/Seoul")))
    db.expire_all()
    assert db.get(AgentRun, ctx.run_id).status == "cancelled"
    assert db.get(ActivityGraphRun, ctx.run_id).status == "interrupted"
    slot = db.get(AgentSlot, ctx.agent_id)
    assert slot.locked_by_run_id is None and slot.status == "assigned_idle"
    due = slot.next_tick_at.replace(tzinfo=UTC)
    assert now <= due < now + timedelta(minutes=26)
    spread = SimpleNamespace(next_tick_at=now + timedelta(seconds=20))
    assert recovery_due(spread, now=now, deadline=now+timedelta(seconds=10)) == now
    assert recovery_due(spread, now=now, deadline=now-timedelta(seconds=1)) == spread.next_tick_at


def test_reclaim_uses_saved_generation_once_and_publication_is_idempotent(routine, monkeypatch):
    db, fixture, ctx, prepared, tracker = routine
    generation = asyncio.run(FakeRoutineProvider().generate(resident_context=ctx,
        routine_context=prepared.context, beat=prepared.beat, tracker=tracker))
    frozen = freeze_prepared(prepared, allow_reclaim=True)
    prepared.beat.status = "pending"; prepared.beat.claim_run_id = None; prepared.beat.claim_expires_at = None
    db.commit()
    now = ctx.run_started_at + timedelta(minutes=1)
    from app.runtime.autonomous_activity import routine_resume
    monkeypatch.setattr(routine_resume, "datetime", SimpleNamespace(now=lambda _tz: now, fromisoformat=datetime.fromisoformat))
    restored = restore_prepared(ctx, frozen, tracker)
    assert restored.beat.attempt_count == 2 and restored.beat.id == frozen["beat_id"]
    assert restored.execution_signature == frozen["execution_signature"]
    first = publish_routine_activity(ctx, prepared=restored, generation=generation)
    assert first["routine_outcome"] == "POST_SUCCEEDED", first
    second = publish_routine_activity(ctx, prepared=restored, generation=generation)
    assert second["routine_outcome"] == "REUSED_SUCCESS" and second["publish_result"]["public_action_count"] == 0


@pytest.mark.parametrize("change", ["binding", "window", "attempts", "live_claim", "terminal", "state", "sequence"])
def test_reclaim_keeps_real_window_budget_and_claim_protection(routine, change):
    db, fixture, ctx, prepared, tracker = routine
    frozen = freeze_prepared(prepared, allow_reclaim=True)
    binding = deepcopy(frozen["beat_binding"])
    now = ctx.run_started_at + timedelta(minutes=1)
    prepared.beat.status = "pending"; prepared.beat.claim_run_id = None; prepared.beat.claim_expires_at = None
    if change == "binding": binding["source_event_ids"] = ["invented"]
    if change == "window": now = prepared.context.item.scheduled_end_at.replace(tzinfo=UTC) + timedelta(minutes=1)
    if change == "attempts": prepared.beat.attempt_count = 2
    if change == "live_claim":
        prepared.beat.status = "claimed"; prepared.beat.claim_run_id = "another-run"; prepared.beat.claim_expires_at = now+timedelta(minutes=1)
    if change == "terminal": prepared.beat.status = "failed"
    if change == "state": prepared.context.episode.current_state_snapshot = {"changed": True}
    if change == "sequence": prepared.context.episode.next_sequence_no += 1
    beat_id = prepared.beat.id
    db.commit()
    with pytest.raises(ActivityRuntimeConflictError):
        reclaim_frozen_beat(db, beat_id=beat_id, binding=binding, claim_run_id=ctx.run_id,
            now=now, claim_expires_at=now+timedelta(minutes=10))


def test_cancel_cleanup_failure_rolls_back_run_slot_and_graph(routine):
    db, fixture, ctx, prepared, tracker = routine
    slot = db.get(AgentSlot, ctx.agent_id)
    if slot is None:
        slot = AgentSlot(agent_id=ctx.agent_id); db.add(slot)
    slot.status = "running"; slot.locked_by_run_id = ctx.run_id
    slot.assigned_user_id = ctx.user_id; slot.assigned_character_id = ctx.character.id
    slot.lease_expires_at = ctx.run_started_at + timedelta(minutes=10)
    db.add(ActivityGraphRun(activity_id=ctx.run_id, world_id=fixture.world.id,
        world_character_id=fixture.world_character.id, engine="personalized_graph_v2", contract_version=2,
        status="running", stage="routine.Execute", started_at=ctx.run_started_at, result={}))
    db.commit()
    def fail(session, slot, now):
        session.get(ActivityGraphRun, ctx.run_id).status = "interrupted"
        session.flush()
        raise RuntimeError("synthetic slot scheduling failure")
    with pytest.raises(RuntimeError, match="scheduling failure"):
        cancel_resident_run(db, agent_id=ctx.agent_id, run_id=ctx.run_id, owner_id=ctx.user_id,
            character_id=ctx.character.id, now=ctx.run_started_at, reason=CancellationReason.HEARTBEAT, resolve_schedule=fail)
    db.expire_all()
    assert db.get(ActivityGraphRun, ctx.run_id).status == "running"
    assert db.get(AgentRun, ctx.run_id).status == "running"
    assert db.get(AgentSlot, ctx.agent_id).locked_by_run_id == ctx.run_id
    # Uncommitted caller changes must not be silently discarded by cleanup.
    slot = db.get(AgentSlot, ctx.agent_id); slot.last_error = "caller-owned"
    with pytest.raises(RuntimeError, match="requires_clean_session"):
        cancel_resident_run(db, agent_id=ctx.agent_id, run_id=ctx.run_id, owner_id=ctx.user_id,
            character_id=ctx.character.id, now=ctx.run_started_at, reason=CancellationReason.HEARTBEAT, resolve_schedule=fail)
    assert slot.last_error == "caller-owned" and db.in_transaction()
    db.rollback()
    assert slot.last_error != "caller-owned"
