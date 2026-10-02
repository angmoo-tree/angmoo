import asyncio
from datetime import timedelta
import json

import pytest
from sqlalchemy import select

from app import main
from app.config import settings
from app.domains.routines.models import AgentPublicActionExecution, AgentRun
from app.domains.social.models.posts import Post, PostImageGenerationJob, PostMedia
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import CheckpointRetention, RETENTION_KEY
from app.domains.world_characters.models import WorldCharacter
from app.runtime.autonomous_activity.checkpoint_maintenance import CheckpointMaintenance, protection_reason
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer
from app.runtime.migrations.canonical_retention import ServingRetentionOwner
from retention_support import NOW, checkpoint, completed, database, result

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("failure", [None, "security", "recovery", "component", "memory"])
def test_lifespan_starts_retention_before_workers_and_always_releases(tmp_path, monkeypatch, failure):
    from fastapi import FastAPI
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)
    engine, factory, ids = database(tmp_path)
    calls = []
    owner = ServingRetentionOwner(tmp_path).acquire()
    task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory, clock=lambda: NOW)
    with factory() as db:
        completed(db, ids)
    class Worker:
        def __init__(self, name): self.name = name
        async def start(self):
            calls.append(self.name + ":start")
            assert task._task is not None
            if failure == self.name: raise ValueError("injected_" + self.name)
        async def stop(self): calls.append(self.name + ":stop")
    def stage(name):
        calls.append(name)
        if failure == name: raise ValueError("injected_" + name)
    def dispose():
        calls.append("dispose")
        assert task._task is None
        engine.dispose(); owner.close()
    app = FastAPI()
    app.state.checkpoint_maintenance = task
    lifespan = main.create_public_lifespan(security_validator=lambda: stage("security"),
        startup_recovery=lambda: stage("recovery"), component_manager_factory=lambda: Worker("component"),
        memory_runtime=Worker("memory"), runtime_disposer=dispose)
    async def scenario():
        async with lifespan(app):
            with factory() as db:
                assert db.get(ActivityGraphRun, "old").result[RETENTION_KEY]["state"] == "pruned"
            calls.append("request")
    try:
        if failure:
            with pytest.raises(ValueError, match="injected_"):
                asyncio.run(scenario())
        else:
            asyncio.run(scenario())
        assert calls[-1] == "dispose"
        replacement = ServingRetentionOwner(tmp_path).acquire(); replacement.close()
        assert task._task is None
    finally:
        engine.dispose(); owner.close()


def test_contributor_serving_owner_pin_lifetime_and_diagnostics_authority(tmp_path, monkeypatch):
    from app.runtime.contributor_backend import create_contributor_runtime_app, contributor_runtime_status_payload
    from app.runtime.migrations import canonical_retention
    from app.runtime.migrations.generation import EmbeddedGenerationError
    from migrations.test_canonical_retention import new_copy
    app = create_contributor_runtime_app(data_root=tmp_path)
    try:
        pins = list((tmp_path / "runtime" / "canonical-uses").glob("*.json"))
        assert len(pins) == 1
        with pytest.raises(EmbeddedGenerationError):
            ServingRetentionOwner(tmp_path).acquire()
        relative = json.loads(pins[0].read_text())["relative_path"]
        new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
        original = canonical_retention.prune_generations
        authorities = []
        def prune(root, *, owner):
            authorities.append(owner)
            return original(root, owner=owner)
        monkeypatch.setattr(canonical_retention, "prune_generations", prune)
        contributor_runtime_status_payload(data_root=tmp_path)
        assert authorities == [None]
        assert (tmp_path / "canonical" / relative / "angmoo.sqlite3").exists()
        assert len(list((tmp_path / "runtime" / "canonical-uses").glob("*.json"))) == 1
    finally:
        app.state.dispose_runtime()
    assert list((tmp_path / "runtime" / "canonical-uses").glob("*.json")) == []
    again = create_contributor_runtime_app(data_root=tmp_path)
    try:
        assert not (tmp_path / "canonical" / relative).exists()
        assert again.state.runtime_config.generation == "C"
    finally:
        again.state.dispose_runtime()


@pytest.mark.parametrize("failure", ["listener", "identity", "server_config", None])
def test_sidecar_pre_server_failures_release_use_and_serving_ownership(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    from app.runtime import desktop_sidecar, configuration
    import uvicorn
    root = tmp_path / "data"
    monkeypatch.setattr(desktop_sidecar, "_parse_args", lambda: SimpleNamespace(
        parent_pid=123, data_root=root, runtime_root=root / "runtime",
        legacy_data_root=tmp_path / "absent-legacy", launch_id="fixture",
        runtime_profile="CONTRIBUTOR_EMBEDDED"))
    monkeypatch.setattr(desktop_sidecar, "_is_installer_mode", lambda: False)
    monkeypatch.setattr(desktop_sidecar, "_process_alive", lambda pid: False)
    monkeypatch.setattr(desktop_sidecar.sys, "argv", ["sidecar"])
    monkeypatch.setenv("DESKTOP_LAUNCH_TOKEN", "local-fixture-token-000000000000000000000000000000")
    monkeypatch.setenv("DESKTOP_ALLOWED_ORIGIN", "http://tauri.localhost")
    closed = []
    def fail(*a, **k): raise ValueError("injected sidecar preparation")
    if failure == "listener":
        class Listener:
            def setsockopt(self, *args): pass
            def bind(self, *args): fail()
            def close(self): closed.append(True)
        monkeypatch.setattr(desktop_sidecar.socket, "socket", lambda *a: Listener())
    elif failure == "identity":
        monkeypatch.setattr(configuration, "initialize_local_installation_identity", fail)
    elif failure == "server_config":
        monkeypatch.setattr(uvicorn, "Config", fail)
    if failure:
        with pytest.raises(ValueError, match="injected sidecar preparation"):
            desktop_sidecar.main()
    else:
        assert desktop_sidecar.main() == 0
    if failure == "listener": assert closed == [True]
    assert not (root / "runtime" / "sidecar.owner.json").exists()
    assert list((root / "runtime" / "canonical-uses").glob("*.json")) == []
    replacement = ServingRetentionOwner(root).acquire(); replacement.close()


def test_unconfirmed_worker_shutdown_keeps_generation_pin(tmp_path, monkeypatch):
    from app.runtime.contributor_backend import create_contributor_runtime_app
    from app.runtime.migrations import canonical_retention
    from migrations.test_canonical_retention import new_copy, prune
    app = create_contributor_runtime_app(data_root=tmp_path)
    composition = app.state.runtime_composition
    original = composition.config.database_path
    class Worker:
        async def start(self): pass
        async def stop(self): raise RuntimeError("shutdown unconfirmed")
    lifespan = main.create_public_lifespan(runtime_settings=composition.settings,
        runtime_disposer=app.state.dispose_runtime, memory_runtime=Worker())
    async def scenario():
        async with lifespan(app): pass
    try:
        with pytest.raises(RuntimeError, match="shutdown unconfirmed"):
            asyncio.run(scenario())
        assert composition.engine._angmoo_generation_use_pin is composition.generation_use_pin
        new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
        owner = ServingRetentionOwner(tmp_path).acquire()
        try:
            assert prune(tmp_path, owner).get("removed", 0) == 0 and original.exists()
            # The injected worker has no actual task; only this test can now
            # confirm it is stopped and release the retained safety pin.
            composition.generation_use_pin.close()
            assert prune(tmp_path, owner)["removed"] == 1
        finally:
            owner.close()
    finally:
        composition.generation_use_pin.close()


def test_composition_failure_releases_preopen_pin_and_owner(tmp_path, monkeypatch):
    from app.runtime import configuration
    from app.runtime.contributor_backend import create_contributor_runtime_app
    def fail(*a, **k): raise RuntimeError("injected composition")
    monkeypatch.setattr(configuration, "MemoryHybridRuntime", fail)
    with pytest.raises(RuntimeError, match="injected composition"):
        create_contributor_runtime_app(data_root=tmp_path)
    assert list((tmp_path / "runtime" / "canonical-uses").glob("*.json")) == []
    owner = ServingRetentionOwner(tmp_path).acquire(); owner.close()


def test_received_image_and_attachment_recovery_protect_then_release_checkpoint(tmp_path, monkeypatch):
    from image_integration.test_generation_lifecycle import configured, admit, OWNER, CHARACTER, POST
    sessions, media, provider = configured(tmp_path)
    identity = admit(sessions, media)
    with sessions() as db:
        actor = db.scalar(select(WorldCharacter).where(WorldCharacter.character_id == CHARACTER))
        post = db.get(Post, POST)
        assert actor is not None and post.world_id == actor.world_id
        db.add(AgentRun(id="image-activity", user_id=OWNER, character_id=CHARACTER,
            agent_id="image-slot", session_key="image", status="completed")); db.flush()
        payload = result(count=1)
        payload[RETENTION_KEY] = CheckpointRetention(graph_complete=True).model_dump()
        row = ActivityGraphRun(activity_id="image-activity", world_id=actor.world_id,
            world_character_id=actor.id, engine="personalized_graph_v2", contract_version=2,
            status="completed", stage="Finalize", started_at=NOW-timedelta(days=3),
            finished_at=NOW-timedelta(days=2), result=payload)
        db.add(row)
        db.add(AgentPublicActionExecution(run_id=row.activity_id, character_id=CHARACTER,
            signature="image-published", scope="writing", action_type="post", status="succeeded",
            completed_at=NOW-timedelta(days=2), world_id=actor.world_id, actor_world_character_id=actor.id,
            result={"post_id": POST}))
        db.commit()
        assert protection_reason(db, row, now=NOW) == "image_recovery_pending"
    attach = media.worker._attach
    def postpone(db, job):
        job.status = "result_ready"; db.commit()
    monkeypatch.setattr(media.worker, "_attach", postpone)
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        assert db.get(PostImageGenerationJob, identity).status == "result_ready"
        assert protection_reason(db, db.get(ActivityGraphRun, "image-activity"), now=NOW) == "image_recovery_pending"
        assert db.scalar(select(PostMedia)) is None
    monkeypatch.setattr(media.worker, "_attach", attach)
    asyncio.run(media.worker.process(identity))
    assert provider.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, identity).status == "succeeded"
        assert db.scalar(select(PostMedia)) is not None
        assert protection_reason(db, db.get(ActivityGraphRun, "image-activity"), now=NOW) is None
    async def prune():
        async with activity_checkpointer(tmp_path) as saver:
            await checkpoint(saver, "image-activity")
        task = CheckpointMaintenance(data_root=tmp_path, session_factory=sessions, clock=lambda: NOW)
        assert (await task.cycle())["pruned"] == 1
    asyncio.run(prune())
    with sessions() as db:
        assert db.scalar(select(PostMedia)) is not None and provider.calls == 1


def test_same_root_generation_and_checkpoint_failures_preserve_completed_result(tmp_path, monkeypatch):
    from dataclasses import replace
    from pathlib import Path
    from app.runtime.contributor_backend import create_contributor_runtime_app
    from app.domains.routines.models import AgentSlot
    from app.domains.world_characters.service.activity_engines import bind_run
    from app.runtime.autonomous_activity.binding import ActivityRuntimeBinding, register, unregister
    from app.runtime.autonomous_activity.execution import run_personalized_activity
    from app.runtime.autonomous_activity.provider import ActivityProvider
    from app.runtime.autonomous_activity.planner_contract import parse_action
    from social.test_feed_reaction_intent import _seed
    from app.domains.world_characters.models import CharacterActiveWorld
    from app.domains.characters.models import Character
    from app.domains.identity.models import LlmCredential
    from migrations.test_canonical_retention import new_copy
    from app.runtime.migrations import embedded_sqlite
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    app = create_contributor_runtime_app(data_root=tmp_path)
    binding = ActivityRuntimeBinding(None, tmp_path)
    register(binding)
    calls = []
    async def plan(self, **kwargs):
        calls.append("model")
        kwargs["delivery"].dispatched(); kwargs["delivery"].delivered()
        return {**parse_action({"decisions": [{"target_id": post_id, "action": "like", "brief": "A useful discovery"}]}, kwargs["candidates"]),
            "judged_at": NOW.isoformat(), "provisional_draft": {"replies": []}}
    monkeypatch.setattr(ActivityProvider, "plan", plan)
    original_database = app.state.runtime_config.database_path
    try:
        with app.state.runtime_composition.session_factory() as db:
            ctx, post = _seed(db, with_candidate=True)
            post_id = post.id
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                assigned_user_id=ctx.user_id, assigned_character_id=ctx.character.id, lease_expires_at=NOW+timedelta(days=500)))
            run = bind_run(db, actor=actor, activity_id=ctx.run_id); run.contract_version = 1; db.commit()
            answer = asyncio.run(run_personalized_activity(ctx, actor=actor, run=run))
            finished = run.finished_at
            db.delete(db.get(AgentSlot, ctx.agent_id)); db.commit()
            ctx_ids = (ctx.character.id, actor.id, run.activity_id)
        new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    finally:
        unregister(binding); app.state.dispose_runtime()
    original_unlink = Path.unlink
    def fail_old(path, *args, **kwargs):
        if path == original_database:
            raise OSError("injected old-generation removal")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_old)
    app = create_contributor_runtime_app(data_root=tmp_path)
    try:
        assert app.state.runtime_config.generation == "C" and original_database.exists()
        task = app.state.checkpoint_maintenance
        task.clock = lambda: finished.replace(tzinfo=NOW.tzinfo)+timedelta(days=2)
        original_mark = task._mark
        monkeypatch.setattr(task, "_mark", lambda *a: (_ for _ in ()).throw(OSError("injected mark")))
        assert asyncio.run(task.cycle())["deferred"] == 1
        monkeypatch.setattr(task, "_mark", original_mark)
        assert asyncio.run(task.cycle())["pruned"] == 1
        with app.state.runtime_composition.session_factory() as db:
            character = db.get(Character, ctx_ids[0])
            actor = db.get(WorldCharacter, ctx_ids[1]); run = db.get(ActivityGraphRun, ctx_ids[2])
            credential = db.scalar(select(LlmCredential).where(LlmCredential.character_id == character.id))
            reused = asyncio.run(run_personalized_activity(replace(ctx, db=db, character=character,
                credential=credential), actor=actor, run=run))
            assert reused == answer and calls == ["model"]
    finally:
        app.state.dispose_runtime()
    monkeypatch.setattr(Path, "unlink", original_unlink)
    monkeypatch.setattr(embedded_sqlite, "_backup_database", lambda *a: pytest.fail("unnecessary copy"))
    app = create_contributor_runtime_app(data_root=tmp_path)
    try:
        assert not original_database.parent.exists() and app.state.runtime_config.generation == "C"
        assert calls == ["model"]
    finally:
        app.state.dispose_runtime()


@pytest.mark.parametrize("failure", [False, True])
def test_installer_checkpoint_consumer_pins_selected_generation_without_retention_authority(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    from app.runtime import desktop_sidecar, installer_update
    from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION
    from app.integrations.ladybug_projection import LADYBUG_PROJECTION_SCHEMA_VERSION
    from migrations.test_canonical_retention import clean, new_copy, prune
    from test_installer_update import _manifest
    desktop_sidecar._write_new_secret(tmp_path / "secrets" / "app-secret")
    first = clean(tmp_path)
    manifest = _manifest(tmp_path / "payload.json", sqlite=(1, SQLITE_SCHEMA_VERSION, SQLITE_SCHEMA_VERSION),
        ladybug=(0, LADYBUG_PROJECTION_SCHEMA_VERSION, LADYBUG_PROJECTION_SCHEMA_VERSION))
    args = SimpleNamespace(installer_data_preflight=False, payload_manifest=manifest,
        legacy_data_root=tmp_path.parent / (tmp_path.name + "-missing-legacy"))
    original = installer_update.checkpoint_installer_sqlite
    checkpoints = []
    def checkpoint_selected(database_path):
        checkpoints.append(database_path)
        pins = list((tmp_path / "runtime" / "canonical-uses").glob("*.json"))
        assert len(pins) == 1
        new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
        owner = ServingRetentionOwner(tmp_path).acquire()
        try:
            assert prune(tmp_path, owner).get("removed", 0) == 0
            assert first.canonical.database_path.exists()
        finally:
            owner.close()
        original(database_path)
        if failure: raise OSError("injected installer checkpoint failure")
    monkeypatch.setattr(installer_update, "checkpoint_installer_sqlite", checkpoint_selected)
    operation = lambda: desktop_sidecar._run_installer_operation(args,
        data_root=tmp_path, runtime_root=tmp_path / "runtime", compatibility_context={})
    if failure:
        with pytest.raises(OSError, match="installer checkpoint failure"): operation()
    else:
        assert operation()["status"] == "upgraded"
    assert checkpoints == [first.canonical.database_path]
    assert list((tmp_path / "runtime" / "canonical-uses").glob("*.json")) == []
    owner = ServingRetentionOwner(tmp_path).acquire()
    try:
        assert prune(tmp_path, owner)["removed"] == 1
    finally:
        owner.close()
