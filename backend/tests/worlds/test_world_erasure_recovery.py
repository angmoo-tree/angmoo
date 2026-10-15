"""Actual WAL references and journal recovery, with no operating user data."""
from datetime import UTC, datetime, timedelta
import sqlite3

import pytest
from sqlalchemy import select, text

from app.core.sqlite_concurrency import SqliteBusyRetryExhausted
from app.domains.worlds.models import World
from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem as Item
from app.runtime.world_deletion.cleanup_effects import clean_step, ErasureLeaseLost
from app.runtime.world_deletion.worker import WorldDeletionWorker
from worlds.test_world_deletion import environment, admitted, finish


def survivor(sessions, profile):
    from worlds.test_foundation import _character
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.memory.models.items import MemoryScopeSettingModel
    from app.domains.memory.models.embedding import MemoryEmbeddingSetting
    from app.domains.memory.models.activity_configuration import MemoryIndexPreparation
    with sessions() as db:
        db.add(_character("survivor", "owner"))
        db.flush()
        db.add(WorldCharacter(id="survivor-b", world_id="b", character_id="survivor", membership_id="member-b"))
        db.flush()
        db.add(MemoryScopeSettingModel(id="survivor-memory", owner_id="owner", world_id="b", subject_world_character_id="survivor-b"))
        db.flush()
        db.add(MemoryEmbeddingSetting(scope_setting_id="survivor-memory", provider="google", model="gemini-embedding-2", profile=profile))
        db.add(MemoryIndexPreparation(scope_setting_id="survivor-memory", state="ready", revision=1,
            profile=profile, source_generation="generation"))
        db.commit()


def test_wal_deletion_memory_relationship_and_environment_writers_resume(environment):
    from concurrent.futures import ThreadPoolExecutor
    from app.core.sqlite_concurrency import run_sqlite_session_immediate
    from app.domains.memory.models.items import MemoryItem
    from app.domains.relationships.models.social import RelationshipState
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.identity.service.environment import report_environment, EnvironmentTemporarilyBusy
    from worlds.test_foundation import _character
    from identity.test_local_environment import report
    sessions, ports, _ = environment
    survivor(sessions, "gemini-embedding-2:768")
    path, request_id = file_and_request(sessions, ports)
    with sessions() as db:
        db.add(_character("second", "owner")); db.flush()
        db.add(WorldCharacter(id="second-b", world_id="b", character_id="second", membership_id="member-b")); db.flush()
        db.add(MemoryItem(id="surviving-memory", owner_id="owner", world_id="b", subject_world_character_id="survivor-b",
            memory_kind="AUTOBIOGRAPHICAL_EVENT", summary="Saved experience", confidence=1, salience=1))
        db.add(RelationshipState(id="surviving-relation", world_id="b", actor_world_character_id="survivor-b", target_world_character_id="second-b"))
        db.commit()
    worker = WorldDeletionWorker(sessions, ports)
    def write_memory_relationship():
        with sessions() as db:
            def apply():
                item = db.get(MemoryItem, "surviving-memory")
                item.summary = "Preserved after concurrent writes"
                row = db.get(RelationshipState, "surviving-relation")
                row.interaction_count += 1
            run_sqlite_session_immediate(db, apply, require_clean=True)
    def environment_write():
        with sessions() as db:
            return report_environment(db, "owner", report(), session_hash="synthetic")
    engine = sessions.kw["bind"]
    with engine.connect() as holder, ThreadPoolExecutor(max_workers=3) as executor:
        holder.exec_driver_sql("BEGIN IMMEDIATE")
        deletion_wait = executor.submit(worker.tick)
        memory_wait = executor.submit(write_memory_relationship)
        environment_wait = executor.submit(environment_write)
        assert deletion_wait.result(timeout=5) is False
        for future, expected in ((memory_wait, SqliteBusyRetryExhausted), (environment_wait, EnvironmentTemporarilyBusy)):
            with pytest.raises(expected):
                future.result(timeout=5)
        holder.rollback()
        # All three owners can proceed after contention, without erasing any
        # unfinished journal or misclassifying contention as a terminal defect.
        deletion_done = executor.submit(finish, sessions, ports)
        executor.submit(write_memory_relationship).result(timeout=10)
        executor.submit(environment_write).result(timeout=10)
        assert deletion_done.result(timeout=60).state == "completed"
    with sessions() as db:
        assert db.get(MemoryItem, "surviving-memory").summary == "Preserved after concurrent writes"
        assert db.get(RelationshipState, "surviving-relation").interaction_count == 1
        assert db.get(World, "b").name == "World b"
        assert db.get(WorldDeletionRequest, request_id).failures == 0
    assert not path.exists()


def file_and_request(sessions, ports, *, reference=True):
    engine = sessions.kw["bind"]
    with engine.connect() as db:
        assert db.exec_driver_sql("PRAGMA journal_mode=WAL").scalar() == "wal"
    path = ports.media_root / "worlds/a/owned_%'한글.webp"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"only target world")
    with sessions() as db:
        if reference:
            db.get(World, "a").icon_media_id = "/media/" + path.relative_to(ports.media_root).as_posix()
        db.commit()
    return path, admitted(sessions).request_id


@pytest.mark.parametrize("profile", ["gemini-embedding-2:768", '{"avatar_url":"/media/not-an-image-profile"}'])
def test_string_embedding_profiles_survive_and_do_not_block_file_erasure(environment, profile):
    sessions, ports, _ = environment
    survivor(sessions, profile)
    path, _ = file_and_request(sessions, ports)
    assert finish(sessions, ports).state == "completed"
    assert not path.exists()
    with sessions() as db:
        for table in ("memory_embedding_settings", "memory_index_preparations"):
            assert db.execute(text(f"SELECT profile FROM {table} WHERE scope_setting_id='survivor-memory'")).scalar() == profile


@pytest.mark.parametrize("payload", ["broken-json", '"not an object"', '{"avatar_url":42}'])
def test_actual_invalid_image_profile_fails_before_unlink_and_waits_for_explicit_retry(environment, payload):
    sessions, ports, _ = environment
    survivor(sessions, "ordinary-profile")
    with sessions() as db:
        db.execute(text("UPDATE world_characters SET local_profile=:value WHERE id='survivor-b'"), {"value": payload})
        db.commit()
    path, request_id = file_and_request(sessions, ports)
    assert finish(sessions, ports).state == "failed"
    assert path.exists()
    assert not WorldDeletionWorker(sessions, ports).tick()
    with sessions() as db:
        row = db.get(WorldDeletionRequest, request_id)
        assert row.failures == 1 and row.failure_code == "cleanup_failed"
        db.execute(text("UPDATE world_characters SET local_profile=NULL WHERE id='survivor-b'"))
        db.commit()
        from app.domains.worlds.service.deletion import retry
        assert retry(db, request_id, "owner").request_id == request_id
    assert finish(sessions, ports).state == "completed"
    assert not path.exists()


def cleaning_request(sessions, ports):
    path, request_id = file_and_request(sessions, ports, reference=False)
    with sessions() as db:
        row = db.get(WorldDeletionRequest, request_id)
        row.stage, row.state, row.lease_epoch = "cleaning", "cleaning", 1
        row.lease_until = datetime.now(UTC) + timedelta(seconds=30)
        ports._file(db, row, path.relative_to(ports.media_root).as_posix())
        db.commit()
    return path, request_id


def test_recreated_path_and_expired_worker_cannot_delete_new_file(environment):
    sessions, ports, _ = environment
    path, request_id = cleaning_request(sessions, ports)
    path.unlink()
    path.write_bytes(b"new unrelated generation")
    assert clean_step(sessions, ports, request_id, 1) is False
    with sessions() as db:
        assert db.scalar(select(Item.state)) == "retained"
        db.get(WorldDeletionRequest, request_id).lease_epoch = 2
        db.commit()
    with pytest.raises(ErasureLeaseLost):
        clean_step(sessions, ports, request_id, 1)
    assert path.read_bytes() == b"new unrelated generation"


def test_reference_check_and_unlink_share_short_writer_fence(environment, monkeypatch):
    sessions, ports, _ = environment
    path, request_id = cleaning_request(sessions, ports)
    original = ports._protected_files
    attempts = []
    def protected(db, request, candidates):
        with sessions.kw["bind"].connect() as contender:
            contender.exec_driver_sql("PRAGMA busy_timeout=0")
            from sqlalchemy.exc import OperationalError
            with pytest.raises(OperationalError) as failed:
                contender.exec_driver_sql("BEGIN IMMEDIATE")
            assert failed.value.orig.sqlite_errorcode & 255 == sqlite3.SQLITE_BUSY
            contender.rollback()
        attempts.append(1)
        return original(db, request, candidates)
    monkeypatch.setattr(ports, "_protected_files", protected)
    clean_step(sessions, ports, request_id, 1)
    assert attempts == [1] and not path.exists()
    with sessions.kw["bind"].connect() as contender:
        contender.exec_driver_sql("BEGIN IMMEDIATE")
        contender.rollback()


def test_graph_effect_has_no_writer_and_ack_busy_keeps_failure_budget(environment, monkeypatch):
    sessions, ports, _ = environment
    request_id = admitted(sessions).request_id
    with sessions() as db:
        row = db.get(WorldDeletionRequest, request_id)
        row.stage = row.state = "cleaning"
        ports._journal(db, row, "graph", {"world_id": "a"})
        db.commit()
    effects = set()
    def graph(world):
        with sessions.kw["bind"].connect() as writer:
            writer.exec_driver_sql("PRAGMA busy_timeout=0")
            writer.exec_driver_sql("BEGIN IMMEDIATE")
            writer.rollback()
        effects.add(world)
    ports.graph_cleanup = graph
    from app.runtime.world_deletion import cleanup_effects
    ack = cleanup_effects._ack
    monkeypatch.setattr(cleanup_effects, "_ack", lambda *a, **k: (_ for _ in ()).throw(SqliteBusyRetryExhausted("synthetic busy")))
    worker = WorldDeletionWorker(sessions, ports)
    assert not worker.tick()
    with sessions() as db:
        row = db.get(WorldDeletionRequest, request_id)
        assert row.state == "retry_wait" and row.failures == 0
        assert db.scalar(select(Item.state)) == "pending"
        row.next_attempt_at = None
        db.commit()
    monkeypatch.setattr(cleanup_effects, "_ack", ack)
    assert worker.tick()
    assert effects == {"a"}
    with sessions() as db:
        assert db.scalar(select(Item.state)) == "done"
