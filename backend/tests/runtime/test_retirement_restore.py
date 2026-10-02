"""Real claim settlement and paired SQLite restore of synthetic SNS records."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines.models import AgentSlot
from app.domains.routines.models.plans import ActivityBeat, ActivityEventConsumption
from app.domains.relationships.models.social import SocialEvent
from app.domains.world_characters.activity_models import ActivityGraphRun, ActivityEnginePolicy
from app.domains.world_characters.contracts.checkpoint_retention import RETENTION_KEY, business_result
from app.domains.world_characters.service.activity_engines import bind_run
from app.runtime.autonomous_activity.retirement import transition_uow
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, backup_checkpoint
from app.runtime.autonomous_activity.checkpoint_maintenance import CheckpointMaintenance
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.inputs import shared_input
from app.integrations.direct_llm import RunLlmTracker
from retention_support import database, completed, checkpoint, NOW
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("live", [False, True])
def test_retirement_uses_real_episode_beat_event_and_slot_ownership(monkeypatch, live):
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    engine = _engine()
    async def scenario():
        with Session(engine, expire_on_commit=False) as db:
            fixture = _seed(db)
            ctx = _resident_context(db, fixture, run_id="old-claimed-routine",
                now=_utc(datetime(2026, 8, 10, 10, 5)))
            actor = fixture.world_character
            row = bind_run(db, actor=actor, activity_id=ctx.run_id)
            row.engine, row.contract_version = "current", 1
            row.result = {"usage": {"calls": 2}, "partial_success": "preserved"}
            db.commit()
            async def guard(_):
                return {}
            lane = RoutineLane(ctx, actor=actor, tracker=RunLlmTracker(max_calls=15), hybrid_service=None, guard=guard)
            await lane.load({"identity": {"activity_id": ctx.run_id}, "shared_context": shared_input(ctx, actor, fixture.world)})
            beat = lane.prepared.beat
            episode = lane.prepared.context.episode
            expiry = NOW + timedelta(minutes=1) if live else NOW - timedelta(minutes=1)
            beat.claim_expires_at = expiry
            beat.result_snapshot = {"unexecuted_draft": True}
            db.add(SocialEvent(id="success-before-retirement", world_id=actor.world_id,
                actor_world_character_id=actor.id, event_type="post_published", occurred_at=NOW,
                idempotency_key="historical-success-fixture"))
            db.flush()
            db.add(ActivityEventConsumption(id="old-event-claim", world_id=actor.world_id,
                consumer_world_character_id=actor.id, source_social_event_id="success-before-retirement",
                namespace="next_activity_beat", target_activity_beat_id=beat.id, status="claimed",
                idempotency_key="old-claim", claim_run_id=ctx.run_id, claim_expires_at=expiry, version=2))
            db.add(AgentSlot(agent_id=ctx.agent_id, assigned_character_id=actor.character_id,
                assigned_user_id=ctx.user_id, locked_by_run_id=ctx.run_id, status="running",
                lease_expires_at=NOW-timedelta(minutes=1)))
            db.commit()
            actor_id, beat_id, episode_id = actor.id, beat.id, episode.id
            outcome = transition_uow(db, actor_id=actor_id, now=NOW)
            db.expire_all()
            row = db.get(ActivityGraphRun, ctx.run_id)
            beat = db.get(ActivityBeat, beat_id)
            consumption = db.get(ActivityEventConsumption, "old-event-claim")
            if live:
                assert outcome.state == "pending_settlement" and row.status == "running"
                assert beat.status == "claimed" and consumption.status == "claimed"
            else:
                assert outcome.abandoned_count == 1 and row.status == "abandoned"
                assert beat.status == "failed" and beat.claim_run_id is None
                assert beat.failure_reason_code == "legacy_sns_abandoned"
                assert beat.result_snapshot == {"unexecuted_draft": True}
                assert beat.source_post_id is None and beat.state_after_snapshot is None
                assert consumption.status == "released" and consumption.version == 3
                assert db.get(AgentSlot, ctx.agent_id).locked_by_run_id is None
                assert db.get(type(episode), episode_id).next_sequence_no == beat.sequence_no + 1
                assert row.result["usage"] == {"calls": 2} and RETENTION_KEY not in row.result
            assert db.get(SocialEvent, "success-before-retirement").result == "succeeded"
    try:
        asyncio.run(scenario())
    finally:
        engine.dispose()


def test_paired_backup_restore_keeps_original_and_pruned_completion_while_retiring_old(tmp_path, monkeypatch):
    from app.runtime.migrations.embedded_sqlite import _backup_database
    from app.runtime.autonomous_activity.execution import run_personalized_activity
    from app.runtime.autonomous_activity.provider import ActivityProvider
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.routines.models import AgentRun
    source, archive, restored = (tmp_path / name for name in ("source", "archive", "restored"))
    engine, factory, ids = database(source)
    async def snapshot():
        with factory() as db:
            completed(db, ids, identifier="pruned-complete")
            actor = db.get(WorldCharacter, ids[2])
            db.add(AgentRun(id="old-restored", user_id=ids[0], character_id=ids[1], agent_id="old-slot",
                session_key="old-sns", status="interrupted", gateway_result={"usage": {"calls": 2}}))
            db.flush()
            db.add(ActivityGraphRun(activity_id="old-restored", world_id=ids[3], world_character_id=ids[2],
                engine="current", contract_version=1, status="interrupted", stage="Routine", started_at=NOW-timedelta(days=40),
                result={"partial_success": {"public_action_count": 1}, "recovery_reservations": ["saved-json"]}))
            db.add(ActivityEnginePolicy(scope_key="character:"+actor.id, world_id=actor.world_id,
                world_character_id=actor.id, engine="current", version=3, updated_at=NOW))
            db.commit()
        async with activity_checkpointer(source) as saver:
            await checkpoint(saver, "pruned-complete")
            await checkpoint(saver, "old-restored", blob=b"unexecuted old detail")
        task = CheckpointMaintenance(data_root=source, session_factory=factory, clock=lambda: NOW)
        assert (await task.cycle())["pruned"] == 1
    asyncio.run(snapshot())
    # The fixture has no scheduler or active serving work. Both stores are
    # quiescent, and the checkpoint snapshot uses the product maintenance lock.
    archive.mkdir()
    _backup_database(source / "canonical-test.sqlite3", archive / "canonical.sqlite3")
    assert backup_checkpoint(source, archive / "activity.sqlite3")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()}
    engine.dispose()
    restored.mkdir()
    # Restore the closed snapshot into a fresh root before opening SQLite.
    # Opening a WAL-mode archive with SQLite's backup API may create SHM/WAL
    # companions in the archive; a restore must leave that original untouched.
    shutil.copyfile(archive / "canonical.sqlite3", restored / "canonical-test.sqlite3")
    detail = restored / "runtime" / "activity" / "activity-checkpoints.sqlite"
    detail.parent.mkdir(parents=True)
    shutil.copyfile(archive / "activity.sqlite3", detail)
    restored_engine, restored_factory, _ = database(restored, seed=False)
    try:
        with restored_factory() as db:
            before = deepcopy(db.get(ActivityGraphRun, "pruned-complete").result)
            db.commit()
            outcome = transition_uow(db, actor_id=ids[2], now=NOW,
                readiness=lambda *a, **k: "legacy_v2_preparation_not_ready")
            assert outcome.abandoned_count == 1 and outcome.state == "needs_preparation"
            old = db.get(ActivityGraphRun, "old-restored")
            assert old.status == "abandoned" and old.result["partial_success"] == {"public_action_count": 1}
            assert old.result["recovery_reservations"] == ["saved-json"] and RETENTION_KEY not in old.result
            done = db.get(ActivityGraphRun, "pruned-complete")
            assert done.result == before and done.result[RETENTION_KEY]["state"] == "pruned"
            actor = db.get(WorldCharacter, ids[2])
            actor.autonomous_enabled = False
            db.commit()
            from app.domains.characters.models import Character
            context = SimpleNamespace(db=db, user_id=ids[0], character=db.get(Character, ids[1]))
            monkeypatch.setattr(ActivityProvider, "__init__", lambda *a, **k: pytest.fail("restored completion must not call provider"))
            assert asyncio.run(run_personalized_activity(context, actor=actor, run=done)) == business_result(before)
            assert db.get(AgentRun, "old-restored").gateway_result["usage"] == {"calls": 2}
            assert db.get(ActivityEnginePolicy, "character:" + ids[2]).engine == "current"
            db.commit()
            assert transition_uow(db, actor_id=ids[2], now=NOW,
                readiness=lambda *a, **k: None).converted_count == 1
            db.commit()
            assert transition_uow(db, actor_id=ids[2], now=NOW).abandoned_count == 0
        async def remaining():
            task = CheckpointMaintenance(data_root=restored, session_factory=restored_factory, clock=lambda: NOW+timedelta(days=60))
            await task.cycle()
            async with activity_checkpointer(restored) as saver:
                assert [item async for item in saver.alist({"configurable": {"thread_id": "activity:old-restored"}})]
                assert [item async for item in saver.alist({"configurable": {"thread_id": "activity:pruned-complete"}})] == []
        asyncio.run(remaining())
        assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()} == hashes
    finally:
        restored_engine.dispose()


def test_historical_v1_canonical_completion_is_reused_without_v1_graph(tmp_path, monkeypatch):
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.characters.models import Character
    from app.runtime.autonomous_activity.execution import run_personalized_activity
    from app.runtime.autonomous_activity.provider import ActivityProvider
    from retention_support import result
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            row = completed(db, ids, identifier="historic-v1", marked=False)
            row.contract_version = 1
            row.result = result(version=1)
            actor = db.get(WorldCharacter, ids[2]); actor.autonomous_enabled = False
            db.commit()
            context = SimpleNamespace(db=db, user_id=ids[0], character=db.get(Character, ids[1]))
            monkeypatch.setattr(ActivityProvider, "__init__", lambda *a, **k: pytest.fail("historical V1 must not construct provider"))
            first = asyncio.run(run_personalized_activity(context, actor=actor, run=row))
            assert first == result(version=1)
            assert first["execution_order"] == ["inbox", "routine", "feed"]
    finally:
        engine.dispose()


def test_gateway_completed_id_precedes_unready_policy_and_other_pending_ids(tmp_path, monkeypatch):
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.characters.models import Character
    from app.runtime.autonomous_activity import gateway
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            row = completed(db, ids, identifier="gateway-completed")
            original = deepcopy(row.result)
            actor = db.get(WorldCharacter, ids[2])
            actor.autonomous_enabled = False
            db.add(ActivityEnginePolicy(scope_key="character:"+actor.id, world_id=actor.world_id,
                world_character_id=actor.id, engine="current", version=3, updated_at=NOW))
            db.commit()
            other = db.get(ActivityGraphRun, "run-feed")
            other.status = "interrupted"
            other.engine, other.contract_version = "personalized_graph_v2", 1
            db.commit()
            ctx = SimpleNamespace(db=db, run_id=row.activity_id, user_id=ids[0],
                                  character=db.get(Character, ids[1]))
            monkeypatch.setattr(gateway, "transition_uow", lambda *a, **k: pytest.fail("completion must precede conversion"))
            assert asyncio.run(gateway.run_social_activity(ctx)) == business_result(original)
            assert db.get(ActivityEnginePolicy, "character:"+actor.id).engine == "current"
            assert db.get(ActivityGraphRun, "run-feed").status == "interrupted"
            assert db.get(ActivityGraphRun, row.activity_id).result == original
    finally:
        engine.dispose()


def test_retirement_in_serving_generation_preserves_pins_and_needs_no_schema_copy(tmp_path, monkeypatch):
    from app.runtime.contributor_backend import create_contributor_runtime_app
    from app.runtime.migrations import embedded_sqlite
    from migrations.test_canonical_retention import new_copy, prune, snapshot
    from runtime.test_activity_retirement import old_activity
    from social.test_feed_reaction_intent import _seed as seed_feed
    app = create_contributor_runtime_app(data_root=tmp_path)
    database_path = app.state.runtime_config.database_path
    try:
        with app.state.runtime_composition.session_factory() as db:
            seed_feed(db, with_candidate=False)
            actor_id = old_activity(db, payload={"retained_usage": 2})
            first = transition_uow(db, actor_id=actor_id, now=NOW)
            assert first.abandoned_count == 1
            db.commit()
            assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 0
        new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
        assert list((tmp_path / "runtime" / "canonical-uses").glob("*.json"))
        assert prune(tmp_path, app.state.runtime_config.serving_retention_owner).get("removed", 0) == 0
        assert database_path.exists()
        secret_media = (snapshot(tmp_path / "secrets"), snapshot(tmp_path / "media"))
    finally:
        app.state.dispose_runtime()
    assert not list((tmp_path / "runtime" / "canonical-uses").glob("*.json"))
    monkeypatch.setattr(embedded_sqlite, "_backup_database", lambda *a: pytest.fail("SNS transition must not create a schema copy"))
    app = create_contributor_runtime_app(data_root=tmp_path)
    try:
        assert app.state.runtime_config.generation == "C"
        assert not database_path.parent.exists()
        assert (snapshot(tmp_path / "secrets"), snapshot(tmp_path / "media")) == secret_media
        with app.state.runtime_composition.session_factory() as db:
            assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 0
            assert db.get(ActivityGraphRun, "old-run").status == "abandoned"
    finally:
        app.state.dispose_runtime()


def test_paired_generation_restore_preserves_marker_manifest_and_legacy_records(tmp_path, monkeypatch):
    from app.runtime.contributor_backend import create_contributor_runtime_app
    from app.runtime.migrations import embedded_sqlite
    from migrations.test_canonical_retention import snapshot
    from runtime.test_activity_retirement import old_activity
    from social.test_feed_reaction_intent import _seed as seed_feed
    source, archive, restored = (tmp_path / name for name in ("generation-source", "generation-archive", "generation-restored"))
    app = create_contributor_runtime_app(data_root=source)
    database_relative = app.state.runtime_config.database_path.relative_to(source)
    original_generation = app.state.runtime_config.generation
    factory = app.state.runtime_composition.session_factory
    try:
        with factory() as db:
            seed_feed(db, with_candidate=False)
            actor_id = old_activity(db, payload={"usage": {"calls": 2}, "partial_success": True})
            row = db.get(ActivityGraphRun, "old-run")
            row.contract_version, row.engine = 1, "personalized_graph_v2"
            db.commit()
        async def prepare():
            async with activity_checkpointer(source) as saver:
                await checkpoint(saver, "old-run", blob=b"original old checkpoint")
        asyncio.run(prepare())
        marker_before = snapshot(source / "canonical")
    finally:
        # Quiesce the synthetic serving instance and release its use pin before
        # copying metadata. This never opens or stops a user runtime.
        app.state.dispose_runtime()
    shutil.copytree(source, archive, ignore=shutil.ignore_patterns("activity-checkpoints.sqlite*"))
    embedded_sqlite._backup_database(source / database_relative, archive / database_relative)
    checkpoint_relative = Path("runtime/activity/activity-checkpoints.sqlite")
    assert backup_checkpoint(source, archive / checkpoint_relative)
    archive_before = snapshot(archive)
    shutil.copytree(archive, restored)
    marker_copy = {key: value for key, value in snapshot(restored / "canonical").items()
                   if not key.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm"))}
    marker_source = {key: value for key, value in marker_before.items()
                     if not key.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm"))}
    assert marker_copy == marker_source
    monkeypatch.setattr(embedded_sqlite,
        "_backup_database", lambda *a: pytest.fail("restoring same schema must not create another generation"))
    app = create_contributor_runtime_app(data_root=restored)
    try:
        assert app.state.runtime_config.generation == original_generation
        with app.state.runtime_composition.session_factory() as db:
            result = transition_uow(db, actor_id=actor_id, now=NOW)
            assert result.abandoned_count == 1
            row = db.get(ActivityGraphRun, "old-run")
            assert row.status == "abandoned" and row.engine == "personalized_graph_v2" and row.contract_version == 1
            assert row.result["usage"] == {"calls": 2} and row.result["partial_success"] is True
            assert RETENTION_KEY not in row.result
            db.commit()
            assert transition_uow(db, actor_id=actor_id, now=NOW).abandoned_count == 0
        async def old_detail_remains():
            async with activity_checkpointer(restored) as saver:
                assert [item async for item in saver.alist({"configurable": {"thread_id": "activity:old-run"}})]
        asyncio.run(old_detail_remains())
    finally:
        app.state.dispose_runtime()
    assert snapshot(archive) == archive_before
    assert {key: value for key, value in snapshot(restored / "canonical").items()
            if not key.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm"))} == marker_copy
