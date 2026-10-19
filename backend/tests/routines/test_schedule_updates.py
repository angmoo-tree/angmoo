"""Bounded schedule writes, real SQLite ordering, and frozen activity inputs."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.config import settings
from app.contracts.language import sns_query_language_instruction
from app.domains.identity.models_environment import LocalEnvironment
from app.domains.identity.service.environment import lock_environment_admission, snapshot
from app.domains.routines.models import AgentSlot, AgentRun, AgentActivitySetting
from app.domains.routines.service import slot_leases
from app.domains.routines.service.schedule_updates import changed_schedule
from app.domains.routines.service.tick_schedule import aware_utc, is_within_active_hours
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
from app.domains.world_characters.schemas.management import WorldCharacterSettingsPatch, ExpectedWorldRevision
from app.domains.world_characters.schemas.basic_activity import BasicActivitySettingsPatch
from app.domains.world_characters.service.management import WorldManagementError
from app.runtime.resident import slots
from app.runtime.routines import schedule_updates as runtime
from app.runtime.routines.configuration_reads import capture_activity_input
from app.runtime.world_characters.management import management_service
from world_configuration_fixture_support import fixture_owner
from routines.test_world_independent_autonomy import engine, intent, reconcile_world_autonomy, NOW

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(runtime, "utc_now", lambda: NOW)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is not None else NOW.replace(tzinfo=None)
    monkeypatch.setattr(slot_leases, "datetime", FixedDateTime)
    monkeypatch.setattr("app.runtime.routines.world_autonomy.datetime", FixedDateTime)
    monkeypatch.setattr("app.domains.routines.service.slot_requests.datetime", FixedDateTime)
    monkeypatch.setattr(settings, "RESIDENT_TICK_INITIAL_SPREAD_SECONDS", 0)
    monkeypatch.setattr(settings, "RESIDENT_TICK_ACTIVE_START_SPREAD_SECONDS", 0)


def assigned(db, suffix="a"):
    return db.scalar(select(AgentSlot).where(AgentSlot.assigned_character_id == f"config-actor-{suffix}"))


def setup_idle(db, *, second=False):
    for suffix in (("a", "b") if second else ("a",)):
        stored = db.get(WorldCharacterConfiguration, f"config-role-{suffix}")
        stored.settings = {**stored.settings, "active_hours_start": "00:00", "active_hours_end": "15:00"}
        db.commit()
        intent(db, suffix, True)
    reconcile_world_autonomy(db)
    row = assigned(db)
    row.next_tick_at = NOW + timedelta(days=1)
    row.last_run_at = NOW - timedelta(hours=4)
    row.last_error = "world_active_hours_waiting"
    db.commit()
    return row


def edit(db, *, basic=False, expected=None, **changes):
    role = db.get(WorldCharacter, "config-role-a")
    args = dict(world_id=role.world_id, world_character_id=role.id, user=fixture_owner(db))
    revision = role.version if expected is None else expected
    service = management_service(db)
    if basic:
        return service.patch_activity_settings(**args, data=BasicActivitySettingsPatch(expected_revision=revision, **changes))
    return service.patch_settings(**args, data=WorldCharacterSettingsPatch(expected_revision=revision, settings=changes))


def new_hours(db, **options):
    return edit(db, active_hours_start="12:00", active_hours_end="03:00", **options)


def state(slot):
    return {column.name: deepcopy(getattr(slot, column.name)) for column in AgentSlot.__table__.columns}


def admit(db):
    row = assigned(db)
    row.next_tick_at = NOW - timedelta(seconds=1)
    # Current settings permit NOW. Old future reservations are separately tested.
    stored = db.get(WorldCharacterConfiguration, "config-role-a")
    stored.settings = {**stored.settings, "active_hours_start": "09:00", "active_hours_end": "02:00"}
    db.commit()
    claimed = slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)
    assert len(claimed) == 1
    return claimed[0]


def completion(db, run_id, admitted, *, last_error=None, automatic=True):
    resolver = runtime.automatic_completion_schedule(owner_id="fixture-owner", character_id="config-actor-a",
        input_snapshot=admitted, automatic=automatic)
    slot_leases.complete_resident_slot_run(db, agent_id=assigned(db).agent_id, run_id=run_id,
        heartbeat_interval_seconds=1800, next_tick_at=NOW + timedelta(days=2),
        last_error=last_error, schedule_resolver=resolver)


@pytest.mark.parametrize("basic", [False, True])
def test_time_save_replaces_old_future_and_returns_current_dashboard(engine, basic):
    with Session(engine) as db:
        row = setup_idle(db, second=True)
        before_other = state(assigned(db, "b"))
        old_last = row.last_run_at
        common = db.get(AgentActivitySetting, "config-actor-a").activity_interval_minutes
        new_hours(db, basic=basic)
        db.refresh(row)
        assert aware_utc(row.next_tick_at) == NOW
        assert row.last_run_at == old_last and row.last_error is None
        assert before_other == state(assigned(db, "b"))
        assert db.get(AgentActivitySetting, "config-actor-a").activity_interval_minutes == common
        dashboard = management_service(db).dashboard(world_id="config-world-a", user=fixture_owner(db))
        item = next(item for item in dashboard.items if item.profile.character_id == "config-actor-a")
        assert datetime.fromisoformat(item.next_activity_at).replace(tzinfo=UTC) == NOW
        assert item.autonomous_enabled and item.settings.active_hours_start == "12:00"
        assert db.query(AgentRun).count() == 0
    with Session(engine) as reopened:
        assert aware_utc(assigned(reopened).next_tick_at) == NOW
        assert len(slots.claim_due_resident_slots(reopened, now=NOW, max_count=1, lease_seconds=120)) == 1


def test_baseline_stale_future_is_reproduced_when_schedule_participation_is_absent(engine, monkeypatch):
    with Session(engine) as db:
        row = setup_idle(db)
        old = row.next_tick_at
        # The former management path stored configuration without this collaborator.
        with monkeypatch.context() as context:
            context.setattr(runtime.WorldActivityScheduleUpdater, "refresh", lambda *a, **k: "unconnected")
            new_hours(db)
        assert assigned(db).next_tick_at == old
        intent(db, "a", False)
        intent(db, "a", True)
        assert aware_utc(assigned(db).next_tick_at) == NOW


@pytest.mark.parametrize("minutes,last_minutes,expected_minutes", [(5, 10, 20), (30, 10, 20),
    (60, 10, 50), (120, 60, 60), (60, 180, 0)])
def test_changed_interval_has_one_minimum_and_preserves_last_completion(minutes, last_minutes, expected_minutes):
    policy = SimpleNamespace(activity_interval_minutes=minutes, active_hours_start="09:00", active_hours_end="02:00")
    value = changed_schedule(policy, character_id="fixture", now=NOW,
        last_run_at=NOW-timedelta(minutes=last_minutes), timezone=ZoneInfo("UTC"))
    assert value.next_tick_at == NOW+timedelta(minutes=expected_minutes)
    assert value.target_interval_seconds == max(1800, minutes*60)


@pytest.mark.parametrize("start,end,now,zone,expected", [
    ("12:00", "03:00", "2026-10-05T03:00:00+00:00", "UTC", "2026-10-05T12:00:00+00:00"),
    ("12:00", "03:00", "2026-10-05T01:00:00+00:00", "UTC", "2026-10-05T01:00:00+00:00"),
    ("09:00", "24:00", "2026-10-05T00:00:00+00:00", "UTC", "2026-10-05T09:00:00+00:00"),
    ("12:00", "03:00", "2026-10-05T03:00:00+00:00", "Asia/Seoul", "2026-10-05T03:00:00+00:00"),
    ("09:00", "15:00", "2026-03-08T06:00:00+00:00", "America/New_York", "2026-03-08T13:00:00+00:00"),
    ("09:00", "15:00", "2026-11-01T05:00:00+00:00", "America/New_York", "2026-11-01T14:00:00+00:00"),
])
def test_time_window_and_dst_use_existing_calendar(start, end, now, zone, expected):
    policy = SimpleNamespace(activity_interval_minutes=30, active_hours_start=start, active_hours_end=end)
    value = changed_schedule(policy, character_id="fixture", now=datetime.fromisoformat(now),
        last_run_at=None, timezone=ZoneInfo(zone))
    assert value.next_tick_at == datetime.fromisoformat(expected)
    assert is_within_active_hours(policy, value.next_tick_at, timezone=ZoneInfo(zone))


def test_existing_spread_is_retained(monkeypatch):
    monkeypatch.setattr(settings, "RESIDENT_TICK_INITIAL_SPREAD_SECONDS", 120)
    policy = SimpleNamespace(activity_interval_minutes=30, active_hours_start="09:00", active_hours_end="02:00")
    value = changed_schedule(policy, character_id="config-actor-a", now=NOW, last_run_at=NOW,
                             timezone=ZoneInfo("UTC"))
    assert 0 < value.schedule_spread_seconds <= 120
    assert value.next_tick_at == NOW+timedelta(minutes=30, seconds=value.schedule_spread_seconds)


def test_same_value_unrelated_change_get_and_repeated_on_do_not_write_schedule(engine):
    with Session(engine) as db:
        row = setup_idle(db)
        before = state(row)
        writes = []
        def sql(conn, cursor, statement, parameters, context, executemany):
            if statement.lower().startswith("update agent_slots"):
                writes.append(statement)
        event.listen(engine, "before_cursor_execute", sql)
        try:
            edit(db, active_hours_start="00:00", active_hours_end="15:00")
            edit(db, max_posts_per_day=4)
            intent(db, "a", True)
            management_service(db).dashboard(world_id="config-world-a", user=fixture_owner(db))
        finally:
            event.remove(engine, "before_cursor_execute", sql)
        assert not writes and state(assigned(db)) == before


@pytest.mark.parametrize("released", [False, True])
def test_off_on_uses_new_policy_with_retained_or_reallocated_slot(engine, released):
    with Session(engine) as db:
        setup_idle(db)
        intent(db, "a", False)
        before = state(assigned(db))
        new_hours(db)
        assert state(assigned(db)) == before
        if released:
            reconcile_world_autonomy(db)
            assert assigned(db) is None
        intent(db, "a", True)
        if released:
            assert assigned(db) is None  # management does not allocate
            reconcile_world_autonomy(db)
        row = assigned(db)
        assert row is not None and row.last_error is None
        assert db.get(WorldCharacter, "config-role-a").autonomous_enabled
        effective = db.get(WorldCharacterConfiguration, "config-role-a").settings
        assert effective["active_hours_start"] == "12:00"
        assert aware_utc(row.next_tick_at) == NOW


@pytest.mark.parametrize("status,error,lease,run", [
    ("running", None, 120, "owned"), ("assigned_idle", None, 120, None),
    ("assigned_idle", None, -120, None), ("assigned_idle", None, None, "pending:temporary:manual"),
    ("cooldown", None, None, None), ("unhealthy", "provider_unavailable", None, None),
    ("assigned_idle", "runtime_shutdown", None, None), ("assigned_idle", "credential_cooldown", None, None),
    ("assigned_idle", "world_scope_not_ready", None, None),
])
def test_settings_and_reactivation_preserve_owned_or_retry_slots(engine, status, error, lease, run):
    with Session(engine) as db:
        row = setup_idle(db)
        row.status, row.last_error, row.locked_by_run_id = status, error, run
        row.lease_expires_at = NOW+timedelta(seconds=lease) if lease is not None else None
        db.commit()
        before = state(row)
        new_hours(db)
        intent(db, "a", False)
        intent(db, "a", True)
        assert state(assigned(db)) == before


@pytest.mark.parametrize("status", ["pending", "inactive"])
def test_registration_time_save_does_not_activate_or_allocate(engine, status):
    with Session(engine) as db:
        role = db.get(WorldCharacter, "config-role-a")
        role.status = status
        db.commit()
        new_hours(db, basic=True)
        assert not role.autonomous_enabled and assigned(db) is None
        assert db.query(AgentRun).count() == 0


def test_stale_revision_invalid_input_and_foreign_owner_do_not_change_schedule(engine):
    with Session(engine) as db:
        row = setup_idle(db)
        before = state(row)
        version = db.get(WorldCharacter, "config-role-a").version
        with pytest.raises(WorldManagementError, match="world_character_revision_conflict"):
            new_hours(db, expected=version-1)
        with pytest.raises(ValueError):
            edit(db, active_hours_start="29:00")
        from app.domains.identity.models import User
        with pytest.raises(WorldManagementError):
            management_service(db).patch_settings(world_id="config-world-a", world_character_id="config-role-a",
                user=db.get(User, "fixture-outsider"), data=WorldCharacterSettingsPatch(expected_revision=version,
                    settings={"active_hours_start":"12:00"}))
        assert state(assigned(db)) == before
        assert db.get(WorldCharacter, "config-role-a").version == version


def test_failure_after_schedule_update_rolls_back_configuration_revision_and_schedule(engine, monkeypatch):
    with Session(engine) as db:
        row = setup_idle(db)
        before = state(row)
        stored = deepcopy(db.get(WorldCharacterConfiguration, "config-role-a").settings)
        version = db.get(WorldCharacter, "config-role-a").version
        original = runtime.refresh_idle_schedule
        def failed(*args, **kwargs):
            assert original(*args, **kwargs) == "updated"
            raise RuntimeError("synthetic_schedule_failure")
        monkeypatch.setattr(runtime, "refresh_idle_schedule", failed)
        with pytest.raises(RuntimeError, match="synthetic_schedule_failure"):
            new_hours(db)
        assert state(assigned(db)) == before
        assert db.get(WorldCharacterConfiguration, "config-role-a").settings == stored
        assert db.get(WorldCharacter, "config-role-a").version == version


@pytest.mark.parametrize("bad_scope", ["binding", "owner", "world", "character"])
def test_bound_scope_is_required_before_target_slot_update(engine, bad_scope):
    with Session(engine) as db:
        setup_idle(db, second=True)
        before = [state(assigned(db, s)) for s in ("a", "b")]
        args = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a",
                    character_id="config-actor-a")
        if bad_scope == "binding":
            db.delete(db.get(CharacterActiveWorld, "config-actor-a"))
            db.commit()
        else:
            args[{"owner":"owner_id", "world":"world_id", "character":"character_id"}[bad_scope]] = "foreign"
        with pytest.raises(ValueError, match="activity_schedule_scope_invalid"):
            runtime.WorldActivityScheduleUpdater().refresh(db, **args)
        db.rollback()
        assert [state(assigned(db, s)) for s in ("a", "b")] == before


@pytest.mark.parametrize("automatic,error", [(False, None), (True, "runtime_shutdown"), (True, "provider_failure")])
def test_manual_or_failed_completion_keeps_explicit_next_time(engine, automatic, error):
    with Session(engine) as db:
        setup_idle(db)
        row = admit(db)
        admitted, run_id = deepcopy(row.admission_metadata), row.locked_by_run_id
        new_hours(db, activity_interval_minutes=90)
        completion(db, run_id, admitted, last_error=error, automatic=automatic)
        row = assigned(db)
        assert aware_utc(row.next_tick_at) == NOW+timedelta(days=2)
        assert row.last_error == error and row.admission_metadata == admitted


def test_unchanged_completion_and_replaced_run_keep_original_contract(engine):
    with Session(engine, expire_on_commit=False) as db:
        setup_idle(db)
        row = admit(db)
        admitted, run_id = deepcopy(row.admission_metadata), row.locked_by_run_id
        completion(db, "older-run", admitted)
        db.rollback()
        assert assigned(db).locked_by_run_id == run_id
        completion(db, run_id, admitted)
        assert aware_utc(assigned(db).next_tick_at) == NOW+timedelta(days=2)


@pytest.mark.parametrize("edit_first", [False, True])
def test_completion_and_settings_serialize_in_both_orders_with_stale_identity_map(engine, edit_first):
    with Session(engine) as db:
        setup_idle(db)
        row = admit(db)
        run_id, admitted = row.locked_by_run_id, deepcopy(row.admission_metadata)
        slot_id = row.agent_id
    started = Event()
    def second():
        with Session(engine, expire_on_commit=False) as other:
            stale = other.get(WorldCharacterConfiguration, "config-role-a")
            assert stale.settings["activity_interval_minutes"] != 90
            started.set()
            if edit_first:
                completion(other, run_id, admitted)
            else:
                new_hours(other, activity_interval_minutes=90)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as first:
            lock_environment_admission(first, "fixture-owner")
            future = pool.submit(second)
            assert started.wait(5) and not future.done()
            if edit_first:
                new_hours(first, activity_interval_minutes=90)
            else:
                completion(first, run_id, admitted)
            future.result(timeout=20)
    with Session(engine) as db:
        row = db.get(AgentSlot, slot_id)
        assert aware_utc(row.next_tick_at) == NOW+timedelta(minutes=90)
        assert row.status == "assigned_idle" and row.locked_by_run_id is None
        assert row.admission_metadata == admitted
        assert aware_utc(row.last_run_at) == NOW and row.heartbeat_interval_seconds == 5400


@pytest.mark.parametrize("edit_first", [False, True])
def test_time_edit_and_claim_serialize_without_changing_accepted_snapshot(engine, edit_first):
    with Session(engine) as db:
        setup_idle(db)
        # Outside old hours, inside newly saved ones; force old due work.
        row = assigned(db)
        row.next_tick_at = NOW-timedelta(seconds=1)
        stored = db.get(WorldCharacterConfiguration, "config-role-a")
        stored.settings = {**stored.settings, "active_hours_start":"09:00", "active_hours_end":"02:00"}
        db.commit()
    started = Event()
    def second():
        started.set()
        with Session(engine) as db:
            if edit_first:
                return slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)[0].admission_metadata
            new_hours(db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as db:
            lock_environment_admission(db, "fixture-owner")
            future = pool.submit(second)
            assert started.wait(5) and not future.done()
            if edit_first:
                new_hours(db)
                accepted = future.result(timeout=20)
            else:
                row = slots.claim_due_resident_slots(db, now=NOW, max_count=1, lease_seconds=120)[0]
                accepted = deepcopy(row.admission_metadata)
                future.result(timeout=20)
    assert accepted["_world_configuration"]["settings"]["active_hours_start"] == ("12:00" if edit_first else "09:00")
    with Session(engine) as db:
        assert assigned(db).status == "running" and assigned(db).admission_metadata == accepted


def test_concurrent_same_revision_only_one_schedule_save_commits(engine):
    with Session(engine) as db:
        setup_idle(db)
        version = db.get(WorldCharacter, "config-role-a").version
    started = Event()
    def second():
        started.set()
        with Session(engine) as db:
            with pytest.raises(WorldManagementError, match="world_character_revision_conflict"):
                edit(db, expected=version, active_hours_start="23:00", active_hours_end="00:00")
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as db:
            lock_environment_admission(db, "fixture-owner")
            future = pool.submit(second)
            assert started.wait(5) and not future.done()
            new_hours(db, expected=version)
            future.result(timeout=20)
    with Session(engine) as db:
        assert db.get(WorldCharacter, "config-role-a").version == version+1
        assert aware_utc(assigned(db).next_tick_at) == NOW


def test_language_snapshot_effects_and_new_schedule_have_independent_ownership(engine):
    with Session(engine) as db:
        env = db.get(LocalEnvironment, "fixture-owner")
        assert env is not None
        env.preferred_language, env.timezone = "ko-KR", "UTC"
        env.environment_revision, env.timezone_revision = 1, 1
        db.commit()
        setup_idle(db)
        row = admit(db)
        admitted, run_id = deepcopy(row.admission_metadata), row.locked_by_run_id
        admitted_language = snapshot(db, "fixture-owner").to_dict()
        original_slot = state(row)
        env = db.get(LocalEnvironment, "fixture-owner")
        env.preferred_language, env.timezone = "en-GB", "America/New_York"
        env.environment_revision, env.timezone_revision = 2, 2
        db.commit()
        new_hours(db, activity_interval_minutes=90)
        assert state(assigned(db)) == original_slot
        assert "in Korean." in sns_query_language_instruction(admitted_language["memory_search_locale"])
        assert "in English." in sns_query_language_instruction(snapshot(db, "fixture-owner").memory_search_locale)
        completion(db, run_id, admitted)
        row = assigned(db)
        assert aware_utc(row.next_tick_at) == NOW+timedelta(minutes=90)
        assert row.timezone_revision == 2 and row.admission_metadata == admitted
        assert row.assigned_credential_id == original_slot["assigned_credential_id"]
        assert capture_activity_input(db, character_id="config-actor-a")["_generation_model"] == admitted["_generation_model"]


def test_unassigned_saved_on_retains_new_policy_until_pool_has_capacity(engine, monkeypatch):
    monkeypatch.setattr(settings, "SERVER_LLM_AUTONOMY_MAX_ACTIVE_AGENTS", 1)
    with Session(engine) as db:
        intent(db, "b", True)
        reconcile_world_autonomy(db)
        intent(db, "a", True)
        new_hours(db, activity_interval_minutes=90)
        reconcile_world_autonomy(db)
        assert assigned(db) is None and db.get(WorldCharacter, "config-role-a").autonomous_enabled
        intent(db, "b", False)
        reconcile_world_autonomy(db)
        row = assigned(db)
        assert row is not None and row.heartbeat_interval_seconds == 5400
        assert aware_utc(row.next_tick_at) == NOW
        assert db.query(AgentRun).count() == 0


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_actual_resident_completion_connects_only_normal_schedule_and_preserves_run(engine, monkeypatch, status):
    from app.runtime.resident import execution
    from app.runtime.routines import activity_policy
    policy = activity_policy.build_activity_policy
    monkeypatch.setattr(activity_policy, "build_activity_policy", lambda *a, **kw: policy(*a, **kw, now=NOW))
    monkeypatch.setattr(execution, "current_social_search", lambda: SimpleNamespace(index=None, state=None))
    monkeypatch.setattr(execution, "_select_resident_run_post_id", lambda *a, **kw: None)
    for name, result in (("_format_inbox_threads", ("", False)), ("_format_recent_feed_sections", ("", [])),
        ("_format_recent_own_posts_to_avoid", ""), ("_format_recent_activity_summary", ""),
        ("_format_relationship_review_candidate", ""), ("_format_social_connection_candidate", ""),
        ("_format_strong_social_connection_candidate", "")):
        monkeypatch.setattr(execution, name, lambda *a, _result=result, **kw: _result)
    calls = []
    async def activity(context):
        calls.append(deepcopy(context.input_snapshot))
        new_hours(context.db, activity_interval_minutes=90)
        return {"engine":"synthetic", "status":status, "summary":"preserved synthetic result"}
    monkeypatch.setattr(execution, "run_social_activity", activity)
    with Session(engine) as db:
        setup_idle(db)
        row = admit(db)
        admitted = deepcopy(row.admission_metadata)
        result = asyncio.run(execution._run_resident_slot_once(db, slot=row, post_id=None,
            timeout_seconds=30, message=None, enforce_activity_policy=True))
        assert calls == [admitted] and result.status == status
        stored = db.get(AgentRun, result.run_id)
        assert stored.input_snapshot == admitted and stored.status == status
        assert stored.gateway_result["summary"] == "preserved synthetic result"
        assert assigned(db).locked_by_run_id is None
        if status == "completed":
            assert aware_utc(assigned(db).next_tick_at) == NOW+timedelta(minutes=90)
        else:
            assert assigned(db).heartbeat_interval_seconds != 5400
