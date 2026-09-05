from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier, Event, Lock
from time import monotonic, sleep

import pytest
from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.orm import Session

from app import models
from app.domains.identity.public import LOCAL_INSTALLATION_KEY
from app.domains.runtime.domain.scheduler_lease import (
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    SchedulerTickResult,
)
from app.runtime.graph_projection import SqliteProjectionOutbox
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.core.sqlite_concurrency import (
    SqliteBoundedTaskQueue,
    SqliteRetryPolicy,
    run_sqlite_immediate,
)
from app.exceptions import SqliteBusyRetryExhausted, SqliteTaskQueueFull
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_scheduler_lease import (
    SqliteSchedulerLeaseRepository,
)


NOW = datetime(2026, 8, 20, 1, 30, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self._value = value
        self._lock = Lock()

    def __call__(self) -> datetime:
        with self._lock:
            return self._value

    def advance(self, **delta: float) -> None:
        with self._lock:
            self._value += timedelta(**delta)


def _database(
    tmp_path: Path,
    *,
    generation: str = "concurrency-v1",
    busy_timeout_ms: int = 5_000,
) -> SqliteCanonicalDatabase:
    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(tmp_path / "동시성 앵무 데이터"),
        settings=SqliteCanonicalSettings(
            generation=generation,
            busy_timeout_ms=busy_timeout_ms,
        ),
    )
    database.open()
    return database


def _seed_installation(database: SqliteCanonicalDatabase) -> None:
    with database.session() as session:
        session.add(
            models.InstallationIdentity(
                singleton_key=LOCAL_INSTALLATION_KEY,
                installation_id="installation-concurrency",
                bootstrap_state="unclaimed",
            )
        )
        session.commit()


def _seed_world_and_outbox(database: SqliteCanonicalDatabase) -> None:
    with database.session() as session:
        session.add(
            models.User(
                id="owner-concurrency",
                display_name="SQLite Owner",
                display_name_normalized="sqlite owner",
                profile_setup_completed=True,
            )
        )
        session.add(
            models.Character(
                id="character-concurrency",
                owner_id="owner-concurrency",
                name="Mango",
                handle="mango-sqlite-concurrency",
                persona_summary="A deterministic SQLite concurrency fixture.",
            )
        )
        session.add(
            models.World(
                id="world-concurrency",
                slug="world-sqlite-concurrency",
                owner_user_id="owner-concurrency",
                name="SQLite World",
                contract_version="world-v1",
                contract_hash="a" * 64,
                create_idempotency_key="world-sqlite-concurrency-create",
            )
        )
        session.flush()
        session.add(
            models.WorldMembership(
                id="membership-concurrency",
                world_id="world-concurrency",
                user_id="owner-concurrency",
                role="owner",
                status="active",
            )
        )
        session.flush()
        session.add(
            models.WorldCharacter(
                id="world-character-concurrency",
                world_id="world-concurrency",
                character_id="character-concurrency",
                membership_id="membership-concurrency",
                status="active",
                control_mode="owner_controlled",
                owner_user_id="owner-concurrency",
            )
        )
        session.flush()
        session.add(
            models.SocialEvent(
                id="social-event-concurrency",
                world_id="world-concurrency",
                actor_world_character_id="world-character-concurrency",
                event_type="post_published",
                result="succeeded",
                occurred_at=NOW,
                idempotency_key="social-event-concurrency-key",
                retrieval_status="eligible",
            )
        )
        session.flush()
        session.add(
            models.GraphProjectionOutbox(
                id="outbox-concurrency",
                world_id="world-concurrency",
                source_event_id="social-event-concurrency",
                projection_type="social_event",
                payload={
                    "world_id": "world-concurrency",
                    "source_event_id": "social-event-concurrency",
                    "actor_world_character_id": "world-character-concurrency",
                    "target_world_character_id": None,
                },
                source_signature="b" * 64,
                dedupe_key="outbox-concurrency-dedupe",
                status="pending",
                attempt_count=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()


def _create_manual_post_once(database: SqliteCanonicalDatabase) -> bool:
    ledger = models.OwnerManualSocialWrite.__table__
    post = models.Post.__table__

    def operation(connection: Connection) -> bool:
        existing = connection.execute(
            select(ledger.c.result_post_id).where(
                ledger.c.world_id == "world-concurrency",
                ledger.c.owner_user_id == "owner-concurrency",
                ledger.c.idempotency_key == "same-manual-request",
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False
        connection.execute(
            insert(post).values(
                id="manual-post-concurrency",
                author_user_id="owner-concurrency",
                author_character_id="character-concurrency",
                world_id="world-concurrency",
                author_world_character_id="world-character-concurrency",
                post_type="post",
                visibility="public",
                author_name="Mango",
                title="One canonical post",
                body="Ten simultaneous requests still create one post.",
                search_document="one canonical post",
                created_at=NOW,
                updated_at=NOW,
                report_count=0,
            )
        )
        connection.execute(
            insert(ledger).values(
                id="manual-write-concurrency",
                world_id="world-concurrency",
                owner_user_id="owner-concurrency",
                actor_world_character_id="world-character-concurrency",
                operation="post",
                idempotency_key="same-manual-request",
                request_sha256="c" * 64,
                result_post_id="manual-post-concurrency",
                created_at=NOW,
            )
        )
        return True

    return run_sqlite_immediate(database.engine, operation)


def test_ten_scheduler_claims_have_one_owner_and_expired_lease_is_reclaimed(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _seed_installation(database)
    clock = MutableClock(NOW)
    repository = SqliteSchedulerLeaseRepository(database.engine, clock=clock)
    barrier = Barrier(10)

    def acquire(owner_id: str) -> tuple[str, int] | None:
        barrier.wait()
        try:
            snapshot = repository.acquire(owner_id=owner_id, ttl_seconds=30)
        except SchedulerLeaseHeldError:
            return None
        return owner_id, snapshot.fencing_epoch

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(acquire, [f"scheduler-{index}" for index in range(10)]))

    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    winner_id, winner_epoch = winners[0]
    assert winner_epoch == 1

    clock.advance(seconds=31)
    reclaimed = repository.acquire(owner_id="scheduler-recovered", ttl_seconds=30)
    assert reclaimed.fencing_epoch == 2
    with pytest.raises(SchedulerLeaseLostError):
        repository.heartbeat(
            owner_id=winner_id,
            fencing_epoch=winner_epoch,
            ttl_seconds=30,
        )
    database.close()


def test_sqlite_scheduler_heartbeat_preserves_failure_until_next_tick(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _seed_installation(database)
    clock = MutableClock(NOW)
    repository = SqliteSchedulerLeaseRepository(database.engine, clock=clock)
    lease = repository.acquire(owner_id="scheduler-error", ttl_seconds=30)

    failed = repository.finish_tick(
        owner_id="scheduler-error",
        fencing_epoch=lease.fencing_epoch,
        result=SchedulerTickResult.FAILED,
        error_code="TypeError",
    )
    clock.advance(seconds=5)
    heartbeat = repository.heartbeat(
        owner_id="scheduler-error",
        fencing_epoch=lease.fencing_epoch,
        ttl_seconds=30,
    )

    assert failed.last_error_code == "TypeError"
    assert heartbeat.last_error_code == "TypeError"

    permit = repository.begin_tick(
        owner_id="scheduler-error",
        fencing_epoch=lease.fencing_epoch,
        ttl_seconds=30,
        interval_seconds=60,
    )
    assert permit.should_run is True
    after_begin = repository.heartbeat(
        owner_id="scheduler-error",
        fencing_epoch=lease.fencing_epoch,
        ttl_seconds=30,
    )
    assert after_begin.last_error_code is None

    completed = repository.finish_tick(
        owner_id="scheduler-error",
        fencing_epoch=lease.fencing_epoch,
        result=SchedulerTickResult.SUCCESS,
    )
    assert completed.last_error_code is None
    database.close()


def test_ten_same_manual_requests_commit_one_public_write(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _seed_world_and_outbox(database)
    barrier = Barrier(10)

    def write_once(_index: int) -> bool:
        barrier.wait()
        return _create_manual_post_once(database)

    with ThreadPoolExecutor(max_workers=10) as executor:
        created = list(executor.map(write_once, range(10)))

    assert created.count(True) == 1
    with Session(database.engine) as session:
        assert session.scalar(select(func.count(models.Post.id))) == 1
        assert session.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 1
    database.close()


def test_outbox_claim_has_one_owner_and_expired_claim_is_reclaimed(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _seed_world_and_outbox(database)
    outbox = SqliteProjectionOutbox(database.engine)
    barrier = Barrier(10)

    def claim(worker_id: str) -> tuple[str, ...]:
        barrier.wait()
        return tuple(
            item.id
            for item in outbox.claim(
                worker_id=worker_id,
                now=NOW,
                batch_size=1,
            )
        )

    workers = [f"projector-{index}" for index in range(10)]
    with ThreadPoolExecutor(max_workers=10) as executor:
        claims = list(executor.map(claim, workers))

    owners = [workers[index] for index, result in enumerate(claims) if result]
    assert len(owners) == 1
    first_owner = owners[0]
    with Session(database.engine) as session:
        row = session.get(models.GraphProjectionOutbox, "outbox-concurrency")
        assert row is not None
        assert row.status == "processing"
        assert row.attempt_count == 1
        assert session.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert session.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 1

    assert (
        outbox.finalize_success(
            outbox_id="outbox-concurrency",
            worker_id="stale-worker",
            now=NOW + timedelta(seconds=1),
        )
        == "lease_lost"
    )
    reclaimed = outbox.claim(
        worker_id="projector-recovered",
        now=NOW + timedelta(seconds=61),
        batch_size=1,
    )
    assert [item.id for item in reclaimed] == ["outbox-concurrency"]
    assert (
        outbox.finalize_success(
            outbox_id="outbox-concurrency",
            worker_id=first_owner,
            now=NOW + timedelta(seconds=62),
        )
        == "lease_lost"
    )
    assert (
        outbox.finalize_success(
            outbox_id="outbox-concurrency",
            worker_id="projector-recovered",
            now=NOW + timedelta(seconds=62),
        )
        == "succeeded"
    )
    with Session(database.engine) as session:
        row = session.get(models.GraphProjectionOutbox, "outbox-concurrency")
        assert row is not None
        assert row.status == "succeeded"
        assert row.attempt_count == 2
    database.close()


def test_scheduler_user_and_scheduler_projector_competition_preserve_both_writes(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _seed_installation(database)
    _seed_world_and_outbox(database)
    scheduler = SqliteSchedulerLeaseRepository(database.engine, clock=lambda: NOW)
    projector = SqliteProjectionOutbox(database.engine)

    first_barrier = Barrier(2)

    def scheduler_claim() -> int:
        first_barrier.wait()
        return scheduler.acquire(owner_id="scheduler-one", ttl_seconds=30).fencing_epoch

    def user_write() -> bool:
        first_barrier.wait()
        return _create_manual_post_once(database)

    with ThreadPoolExecutor(max_workers=2) as executor:
        scheduler_future = executor.submit(scheduler_claim)
        user_future = executor.submit(user_write)
        assert scheduler_future.result() == 1
        assert user_future.result() is True

    scheduler.release(owner_id="scheduler-one", fencing_epoch=1)
    second_barrier = Barrier(2)

    def recovered_scheduler_claim() -> int:
        second_barrier.wait()
        return scheduler.acquire(owner_id="scheduler-two", ttl_seconds=30).fencing_epoch

    def projector_claim() -> tuple[str, ...]:
        second_barrier.wait()
        return tuple(
            item.id
            for item in projector.claim(
                worker_id="projector-one",
                now=NOW,
                batch_size=1,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        scheduler_future = executor.submit(recovered_scheduler_claim)
        projector_future = executor.submit(projector_claim)
        assert scheduler_future.result() == 2
        assert projector_future.result() == ("outbox-concurrency",)

    with Session(database.engine) as session:
        assert session.scalar(select(func.count(models.Post.id))) == 1
        assert session.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 1
        assert session.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert session.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 1
    database.close()


def test_precommit_crash_rolls_back_and_postcommit_crash_reclaims_after_expiry(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _seed_world_and_outbox(database)
    table = models.GraphProjectionOutbox.__table__

    with database.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.execute(
            update(table)
            .where(table.c.id == "outbox-concurrency")
            .values(
                status="processing",
                lease_owner="crashed-before-commit",
                lease_expires_at=NOW + timedelta(seconds=60),
                attempt_count=table.c.attempt_count + 1,
            )
        )
        connection.rollback()

    with Session(database.engine) as session:
        row = session.get(models.GraphProjectionOutbox, "outbox-concurrency")
        assert row is not None
        assert row.status == "pending"
        assert row.attempt_count == 0

    outbox = SqliteProjectionOutbox(database.engine)
    assert outbox.claim(worker_id="crashed-after-commit", now=NOW, batch_size=1)
    assert (
        outbox.claim(
            worker_id="too-early",
            now=NOW + timedelta(seconds=59),
            batch_size=1,
        )
        == ()
    )
    reclaimed = outbox.claim(
        worker_id="recovered-after-expiry",
        now=NOW + timedelta(seconds=61),
        batch_size=1,
    )
    assert [item.id for item in reclaimed] == ["outbox-concurrency"]
    database.close()


def test_wal_committed_data_survives_checkpoint_close_and_reopen(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path, generation="wal-reopen-v1")

    def operation(connection: Connection) -> None:
        connection.execute(
            insert(models.User.__table__).values(
                id="wal-owner",
                display_name="WAL Owner",
                display_name_normalized="wal owner",
                profile_setup_completed=True,
            )
        )

    run_sqlite_immediate(database.engine, operation)
    assert database.checkpoint()[0] == 0
    database.close()

    doctor = database.open()
    assert doctor.journal_mode == "WAL"
    assert doctor.schema_digest_matches is True
    with Session(database.engine) as session:
        assert session.get(models.User, "wal-owner") is not None
    database.close()


def test_committed_wal_survives_worker_killed_during_blocked_checkpoint(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path, generation="wal-crash-v1")
    database_path = database.database_path
    sentinel = tmp_path / "checkpoint-started"
    reader = sqlite3.connect(database_path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM users").fetchone()
    child_code = "\n".join(
        (
            "from pathlib import Path",
            "import sqlite3, sys",
            "db = sqlite3.connect(sys.argv[1])",
            "db.execute('PRAGMA busy_timeout = 5000')",
            "db.execute(\"INSERT INTO users "
            "(id, display_name, is_admin, profile_setup_completed, feed_content_filter) "
            "VALUES ('checkpoint-owner', 'Checkpoint Owner', 0, 1, 'default')\")",
            "db.commit()",
            "Path(sys.argv[2]).write_text('committed', encoding='utf-8')",
            "db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()",
            "db.close()",
        )
    )
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(database_path), str(sentinel)]
    )
    deadline = monotonic() + 5
    while not sentinel.exists() and monotonic() < deadline:
        sleep(0.01)
    assert sentinel.read_text(encoding="utf-8") == "committed"
    sleep(0.05)
    process.terminate()
    process.wait(timeout=5)
    reader.rollback()
    reader.close()
    database.close()

    doctor = database.open()
    assert doctor.schema_digest_matches is True
    with Session(database.engine) as session:
        assert session.get(models.User, "checkpoint-owner") is not None
    assert database.checkpoint(truncate=True)[0] == 0
    database.close()


def test_busy_retry_is_bounded_and_succeeds_after_lock_release(tmp_path: Path) -> None:
    database = _database(
        tmp_path,
        generation="busy-v1",
        busy_timeout_ms=10,
    )
    holder = database.engine.connect()
    holder.exec_driver_sql("BEGIN IMMEDIATE")
    policy = SqliteRetryPolicy(
        max_attempts=3,
        initial_delay_seconds=0.005,
        maximum_delay_seconds=0.01,
        maximum_elapsed_seconds=0.08,
    )
    started = monotonic()
    with pytest.raises(SqliteBusyRetryExhausted) as error:
        run_sqlite_immediate(database.engine, lambda _connection: None, retry_policy=policy)
    assert error.value.reason_code == "sqlite_busy_retry_exhausted"
    assert monotonic() - started < 1

    holder.rollback()
    holder.close()
    assert (
        run_sqlite_immediate(
            database.engine,
            lambda _connection: "available",
            retry_policy=policy,
        )
        == "available"
    )
    database.close()


def test_sidecar_task_queue_rejects_work_past_bounded_capacity() -> None:
    entered = Event()
    release = Event()

    def blocking_task() -> str:
        entered.set()
        assert release.wait(timeout=2)
        return "done"

    with SqliteBoundedTaskQueue(max_workers=1, capacity=1) as queue:
        future = queue.submit(blocking_task)
        assert entered.wait(timeout=2)
        with pytest.raises(SqliteTaskQueueFull) as error:
            queue.submit(lambda: "overflow")
        assert error.value.reason_code == "sqlite_task_queue_full"
        release.set()
        assert future.result(timeout=2) == "done"
