import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, func, create_engine
from sqlalchemy.orm import sessionmaker
from memory.test_p8_l_r_memory_batch_safety import memory_session, _stack, _save
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
from app.domains.memory.models.batch import MemoryBatchProfile
from app.domains.memory.schemas.batch import MemoryBatchStart
from app.domains.memory.service import consolidation_requests as service
from app.domains.relationships.models.manual_review import RelationshipReviewRequest
from app.domains.relationships.models.personalization import RelationshipPolicy, RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.service.daily_review import plan_review, apply_review, run_review_step
from app.runtime.memory.composition import memory_batch_repository
from app.runtime.memory_http import build_memory_workflows
from app.runtime.relationships.manual_review import ManualRelationshipFollowup
from app.runtime.relationships.manual_review_worker import advance_manual_requests
from test_relationship_daily_review import Provider, References


@pytest.fixture(autouse=True)
def legacy_memory_generation(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "MEMORY_GENERATION_POLICY", "activity32")


def setup(db):
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope, schedule_enabled=False)
    db.add(RelationshipPolicy(world_id=scope.world_id, mode="interpreted", activated_at=datetime.now(UTC)-timedelta(days=1)))
    db.commit()
    workflows = replace(build_memory_workflows(), validate_provider=lambda *args: None)
    saved = repo.settings(scope)
    data = MemoryBatchStart(idempotency_key=uuid4().hex, expected_version=saved.version,
        expected_profile_version=saved.profile_version, expected_scope_version=setting.version, followup="relationships")
    return scope, setting, workflows, data


def finish_memory(db, identifier):
    row = db.get(MemoryConsolidationRequest, identifier)
    row.state = "queued"  # no jobs: production preparation has established no_work
    db.commit()


def memories(db, scope, monkeypatch, count=2):
    payloads = []
    for i in range(count):
        item = MemoryItem(id=f"manual-m-{i}", owner_id=scope.owner_id, world_id=scope.world_id,
            subject_world_character_id=scope.subject_world_character_id, memory_kind="AUTOBIOGRAPHICAL_EVENT",
            summary="상대가 실제로 도와주었다.", confidence=1, salience=1)
        db.add(item)
        payloads.append(dict(memory_id=item.id, summary=item.summary, digest="a"*64, source_refs=[f"post:{i}"], occurred_at=datetime.now(UTC).isoformat()))
    db.commit()
    target = "consolidation-counterpart"
    def collect(db, **kwargs):
        claimed = set(db.scalars(select(RelationshipReviewMemoryReceipt.memory_id)))
        return {target: [m for m in payloads if m["memory_id"] not in claimed]}
    monkeypatch.setattr("app.runtime.relationships.manual_review_worker.collect_new_review_memories", collect)
    monkeypatch.setattr("app.runtime.relationships.manual_review_worker.resolve_memory_batch",
        lambda db, **kw: [(target, next(m for m in payloads if m["memory_id"] == item.id), None) for item in kw["items"]])
    return target, payloads


def test_atomic_admission_replay_coalesce_and_pure_read(memory_session):
    db = memory_session
    scope, setting, workflows, data = setup(db)
    first = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    assert first["flow_state"] == "memory_running"
    assert service.submit(scope=scope, db=db, workflows=workflows, data=data)["request_id"] == first["request_id"]
    finish_memory(db, first["request_id"])
    second = service.submit(scope=scope, db=db, workflows=workflows, data=data.model_copy(update={"idempotency_key": uuid4().hex}))
    assert second["relationship"]["request_id"] == first["request_id"]
    before = db.scalar(select(func.count()).select_from(RelationshipReviewRequest))
    for _ in range(3):
        assert service.read(scope=scope, db=db, workflows=workflows)["progress"]["flow_state"] == "relationship_waiting"
    assert db.scalar(select(func.count()).select_from(RelationshipReviewRequest)) == before
    assert db.scalar(select(func.count()).select_from(RelationshipReviewWork)) == 0


def test_admission_failure_rolls_back_both_receipts(memory_session):
    db = memory_session
    scope, _, workflows, data = setup(db)
    class Broken(ManualRelationshipFollowup):
        def admit(self, scope, row):
            super().admit(scope, row)
            raise RuntimeError("injected admission failure")
    with pytest.raises(RuntimeError):
        service.submit(scope=scope, db=db, workflows=replace(workflows, consolidation_followup=Broken), data=data)
    assert db.scalar(select(func.count()).select_from(RelationshipReviewRequest)) == 0
    assert db.scalar(select(func.count()).select_from(MemoryConsolidationRequest)) == 0


@pytest.mark.parametrize("memory_state", ["preparing", "paused", "cancelled"])
def test_incomplete_memory_never_starts_relationship(memory_session, memory_state):
    db = memory_session
    scope, _, workflows, data = setup(db)
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    row = db.get(MemoryConsolidationRequest, result["request_id"])
    row.state = memory_state
    advance_manual_requests(db, datetime.now(UTC))
    assert db.get(RelationshipReviewRequest, row.id).snapshot is None


@pytest.mark.parametrize("decision", ["keep", "update"])
def test_saved_memories_only_run_without_schedule_and_survive_restart(memory_session, monkeypatch, decision):
    db = memory_session
    scope, _, workflows, data = setup(db)
    _, payloads = memories(db, scope, monkeypatch)
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result["request_id"])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    request = db.get(RelationshipReviewRequest, result["request_id"])
    assert len(request.snapshot) == 2 and len(request.work_ids) == 1
    factory = sessionmaker(db.bind)
    provider = Provider()
    if decision == "keep":
        async def keep(payload, **kwargs):
            provider.calls.append(payload)
            return dict(decision="keep", memory_refs=[m["memory_id"] for m in payload["memories"]])
        provider.review = keep
    work_id = request.work_ids[0]
    assert asyncio.run(run_review_step(factory, work_id=work_id, references_factory=lambda db: References(), provider_factory=lambda base: provider)) == "ready"
    with factory() as reopened:
        apply_review(reopened, work_id=work_id, references=References(), now=datetime.now(UTC)); reopened.commit()
        advance_manual_requests(reopened, datetime.now(UTC)); reopened.commit()
    db.expire_all()
    read = service.read(scope=scope, db=db, workflows=workflows)["progress"]
    assert read["flow_state"] == "completed"
    assert read["relationship"]["kept_count" if decision == "keep" else "changed_count"] == 1
    assert len(provider.calls) == 1
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == len(payloads)
    next_request = service.submit(scope=scope, db=db, workflows=workflows, data=data.model_copy(update={"idempotency_key": uuid4().hex}))
    finish_memory(db, next_request["request_id"])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    assert service.read(scope=scope, db=db, workflows=workflows)["progress"]["flow_state"] == "no_work"


def test_active_automatic_root_does_not_lose_leftover_memory(memory_session, monkeypatch):
    db = memory_session
    scope, setting, workflows, data = setup(db)
    target, payloads = memories(db, scope, monkeypatch)
    root = plan_review(db, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
        target_id=target, period_key="2026-09-22", base={}, memories=payloads[:1]); db.commit()
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result["request_id"])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    request = db.get(RelationshipReviewRequest, result["request_id"])
    assert len(request.snapshot) == 2 and request.work_ids == [root.id]
    # Simulate already verified application; test real application separately above.
    root.status = "applied"
    for receipt in db.scalars(select(RelationshipReviewMemoryReceipt)):
        receipt.status = "applied"
    db.commit()
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    assert len(request.work_ids) == 2
    later = db.get(RelationshipReviewWork, next(i for i in request.work_ids if i != root.id))
    assert [m["memory_id"] for m in later.manifest["memories"]] == [payloads[1]["memory_id"]]
    later.status = "applied"
    for receipt in db.scalars(select(RelationshipReviewMemoryReceipt)):
        receipt.status = "applied"
    db.commit()
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    result = service.read(scope=scope, db=db, workflows=workflows)["progress"]
    assert result["flow_state"] == "completed"
    assert result["relationship"]["target_count"] == result["relationship"]["completed_count"] == 1


def test_v18_migration_preserves_v17_manifest_and_fresh_parity():
    from app.runtime.persistence.sqlite_schema import build_sqlite_v17_metadata, build_sqlite_v23_metadata, build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest, SQLITE_SCHEMA_VERSION
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
    from app.runtime.migrations.sqlite_versions.v17_to_v18_manual_review import capture_delta, upgrade, verify_delta
    with create_engine("sqlite://").begin() as c:
        build_sqlite_v17_metadata().create_all(c); create_schema_version_table(c)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(17).schema_digest
        before = capture_delta(c); upgrade(c); verify_delta(c, before)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(18).schema_digest

        assert not c.exec_driver_sql("PRAGMA foreign_key_check").all()
    with create_engine("sqlite://").begin() as c:
        build_sqlite_v23_metadata().create_all(c); create_schema_version_table(c)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(23).schema_digest
    with create_engine("sqlite://").begin() as c:
        build_sqlite_baseline_metadata().create_all(c); create_schema_version_table(c)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(SQLITE_SCHEMA_VERSION).schema_digest


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_http_admission_has_one_canonical_followup(memory_session, tmp_path, same_key):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    db = memory_session
    scope, _, workflows, data = setup(db)
    path = tmp_path / "concurrent.sqlite3"
    with sqlite3.connect(path) as target:
        db.connection().connection.driver_connection.backup(target)
    engine = create_engine("sqlite:///" + str(path), connect_args={"timeout": 15})
    factory = sessionmaker(engine)
    barrier = Barrier(2)
    def request(i):
        with factory() as session:
            barrier.wait()
            return service.submit(scope=scope, db=session, workflows=workflows,
                data=data if same_key else data.model_copy(update={"idempotency_key": str(i)+uuid4().hex}))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(request, range(2)))
    assert len({r["relationship"]["request_id"] for r in results}) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RelationshipReviewRequest).where(RelationshipReviewRequest.canonical_request_id.is_(None))) == 1
    engine.dispose()


def test_automatic_manual_concurrent_planning_uses_one_root(memory_session, monkeypatch, tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    db = memory_session
    scope, _, _, _ = setup(db)
    target, payloads = memories(db, scope, monkeypatch)
    path = tmp_path / "claims.sqlite3"
    with sqlite3.connect(path) as dest:
        db.connection().connection.driver_connection.backup(dest)
    engine = create_engine("sqlite:///" + str(path), connect_args={"timeout": 15})
    factory = sessionmaker(engine)
    barrier = Barrier(2)
    def claim(period):
        with factory() as session:
            barrier.wait()
            root = plan_review(session, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
                target_id=target, period_key=period, base={}, memories=payloads)
            identifier = root.id
            session.commit()
            return identifier
    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(claim, ["2026-09-22", "manual:test"]))
    assert len(set(ids)) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RelationshipReviewWork)) == 1
        assert session.scalar(select(func.count()).select_from(RelationshipReviewMemoryReceipt)) == 2
    engine.dispose()


def test_frozen_snapshot_ignores_late_memory(memory_session, monkeypatch):
    db = memory_session
    scope, _, workflows, data = setup(db)
    _, payloads = memories(db, scope, monkeypatch)
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result["request_id"])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    request = db.get(RelationshipReviewRequest, result["request_id"])
    frozen = list(request.snapshot)
    payloads.append({**payloads[0], "memory_id": "late-memory"})
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    assert request.snapshot == frozen
    assert len(request.work_ids) == 1


def test_retry_preserves_provider_backoff_and_completed_parts(memory_session, monkeypatch):
    db = memory_session
    scope, _, workflows, data = setup(db)
    memories(db, scope, monkeypatch)
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result["request_id"])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    request = db.get(RelationshipReviewRequest, result["request_id"])
    work = db.get(RelationshipReviewWork, request.work_ids[0])
    work.status, work.error_code = "failed", "relationship_provider_rate_limited"
    deadline = datetime.now(UTC)+timedelta(minutes=10)
    work.next_attempt_at = deadline
    db.commit()
    before = work.next_attempt_at
    service.retry(scope=scope, db=db, workflows=workflows, request_id=result["request_id"], key=uuid4().hex, mode="regenerate_failed", expected_revision=0)
    assert work.next_attempt_at == before
    assert service.read(scope=scope, db=db, workflows=workflows)["progress"]["flow_state"] == "relationship_running"


def test_capacity_allows_empty_memory_stage_but_blocks_new_generation(memory_session, monkeypatch):
    from app.runtime.memory.batch_runtime import MemoryBatchRuntime
    from app.domains.memory.repository.batch import SqlAlchemyMemoryBatchRepository
    from memory.test_p8_l_r_memory_batch_safety import _post
    db = memory_session
    scope, _, workflows, data = setup(db)
    original = SqlAlchemyMemoryBatchRepository.settings
    monkeypatch.setattr(SqlAlchemyMemoryBatchRepository, "settings", lambda self, scope: replace(original(self, scope), capacity_blocked=True))
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    runtime = MemoryBatchRuntime(sessionmaker(db.bind), lambda *a: pytest.fail("must not generate"), generation_policy="episode_v1")
    asyncio.run(runtime.tick())
    db.expire_all()
    assert service.read(scope=scope, db=db, workflows=workflows)["progress"]["state"] == "no_work"
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    from app.runtime.memory.source_delivery import install_memory_delivery, uninstall_memory_delivery
    factory = sessionmaker(db.bind)
    install_memory_delivery(factory)
    try:
        _post(db, scope, "capacity-pending", created_at=datetime.now(UTC))
        next_result = service.submit(scope=scope, db=db, workflows=workflows, data=data.model_copy(update={"idempotency_key": uuid4().hex}))
        asyncio.run(runtime.tick()); db.expire_all()
        value = service.read(scope=scope, db=db, workflows=workflows, request_id=next_result["request_id"])["progress"]
        assert value["state"] == "paused" and value["last_code"] == "memory_capacity_reached"
    finally:
        uninstall_memory_delivery(factory)


@pytest.mark.parametrize("partial", [False, True])
def test_failed_memory_jobs_block_followup_and_retry_is_request_scoped(memory_session, monkeypatch, partial):
    from app.domains.memory.models.items import MemoryMaintenanceJob
    from app.domains.memory.models.batch import MemoryBatchRun
    from app.domains.memory.models.consolidation_request import MemoryConsolidationJob
    db = memory_session
    scope, setting, workflows, data = setup(db)
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result["request_id"])
    now = datetime.now(UTC)
    for identifier, state, linked in [("failed", "failed", True), ("unrelated", "failed", False)] + ([("success", "succeeded", True)] if partial else []):
        db.add(MemoryMaintenanceJob(id=identifier, scope_setting_id=setting.id, reason="memory_selection",
            idempotency_key=identifier, status=state, completed_at=now))
        db.flush()
        db.add(MemoryBatchRun(job_id=identifier, scope_setting_id=setting.id, trigger="explicit",
            scope_version=setting.version, settings_version=data.expected_version,
            profile_version=data.expected_profile_version, model_id="gemini-3.1-flash-lite",
            cutoff_sequence=0, candidate_ids_json="[]", available_at=now))
        if linked:
            db.add(MemoryConsolidationJob(request_id=result["request_id"], job_id=identifier))
    db.commit()
    value = service.read(scope=scope, db=db, workflows=workflows)["progress"]
    assert value["state"] == ("partial_failed" if partial else "failed")
    advance_manual_requests(db, now); db.commit()
    assert db.get(RelationshipReviewRequest, result["request_id"]).snapshot is None
    from app.domains.memory.repository.batch import SqlAlchemyMemoryBatchRepository
    requested = []
    monkeypatch.setattr(SqlAlchemyMemoryBatchRepository, "retry_failed", lambda self, scope, **kwargs: requested.extend(kwargs["request_job_ids"]))
    service.retry(scope=scope, db=db, workflows=workflows, request_id=result["request_id"], key=uuid4().hex, mode="regenerate_failed", expected_revision=0)
    assert set(requested) == ({"failed", "success"} if partial else {"failed"})
    assert db.get(MemoryMaintenanceJob, "unrelated").status == "failed"
    if partial:
        assert db.get(MemoryMaintenanceJob, "success").status == "succeeded"


def test_progress_counts_all_roots_and_preserves_partial_success(memory_session, monkeypatch):
    db = memory_session
    scope, _, workflows, data = setup(db)
    target, payloads = memories(db, scope, monkeypatch, count=45)
    from memory.test_p8_l_o_memory_consolidation import _character, _world_character
    db.add(_character("other-character", scope.owner_id, "other")); db.flush()
    db.add(_world_character("other-target", scope.world_id, "other-character", "consolidation-membership")); db.commit()
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result["request_id"])
    request = db.get(RelationshipReviewRequest, result["request_id"])
    roots = []
    for i, payload in enumerate(payloads):
        counterpart = target if i < 44 else "other-target"
        work = plan_review(db, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
            target_id=counterpart, period_key=f"manual:{i}", base={}, memories=[payload])
        work.status = "applied" if i < 44 else "failed"
        work.result = {"decision": "keep"} if i < 44 else None
        receipt = db.scalar(select(RelationshipReviewMemoryReceipt).where(RelationshipReviewMemoryReceipt.memory_id == payload["memory_id"]))
        receipt.status = "applied" if i < 44 else "pending"
        roots.append(work.id)
        db.flush()
    request.snapshot = [{"memory_id": p["memory_id"], "digest": p["digest"], "target_id": target if i < 44 else "other-target"} for i, p in enumerate(payloads)]
    request.work_ids, request.state = roots, "running"
    db.commit()
    value = service.read(scope=scope, db=db, workflows=workflows)["progress"]
    assert value["flow_state"] == "relationship_retry_needed"
    assert value["relationship"]["memory_count"] == 45
    assert value["relationship"]["target_count"] == 2
    assert value["relationship"]["completed_count"] == value["relationship"]["kept_count"] == 1
    service.retry(scope=scope, db=db, workflows=workflows, request_id=result["request_id"], key=uuid4().hex, mode="regenerate_failed", expected_revision=0)
    assert all(db.get(RelationshipReviewWork, identifier).status == "applied" for identifier in roots[:-1])


def test_owner_can_close_failed_review_without_retry_or_erasing_failure(memory_session, monkeypatch):
    db=memory_session
    scope,_,workflows,data=setup(db)
    memories(db,scope,monkeypatch)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data)
    finish_memory(db,result["request_id"])
    advance_manual_requests(db,datetime.now(UTC));db.commit()
    request=db.get(RelationshipReviewRequest,result["request_id"])
    work=db.get(RelationshipReviewWork,request.work_ids[0])
    work.status,work.error_code,work.maintenance="failed","relationship_review_storage_text_invalid",{"hold":"manual"}
    db.commit()
    value=service.read(scope=scope,db=db,workflows=workflows)["progress"]
    assert set(value["actions"])=={"regenerate_failed","close_without_retry"}
    key=uuid4().hex
    closed=service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=key,
        mode="close_without_retry",expected_revision=value["revision"])["progress"]
    assert closed["flow_state"]=="closed" and closed["actions"]==[]
    db.refresh(work)
    assert work.status=="failed" and work.error_code=="relationship_review_storage_text_invalid"
    assert work.maintenance["hold"]=="closed" and work.maintenance["history"]
    assert closed["relationship"]["closed_count"]==1
    # A replay remains idempotent, and later scheduler advancement cannot reopen it.
    service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=key,
        mode="close_without_retry",expected_revision=value["revision"])
    advance_manual_requests(db,datetime.now(UTC));db.commit()
    assert db.get(RelationshipReviewRequest,result["request_id"]).state=="closed"
    receipt=db.get(RelationshipReviewMemoryReceipt,db.scalar(select(RelationshipReviewMemoryReceipt.id)))
    assert receipt.status=="excluded" and receipt.reason=="owner_closed_failure"


def test_old_revision_cannot_retry_after_user_closed(memory_session,monkeypatch):
    db=memory_session
    scope,_,workflows,data=setup(db)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data)
    request=db.get(RelationshipReviewRequest,result["request_id"])
    request.state="paused";db.commit()
    service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,
        mode="close_without_retry",expected_revision=0)
    from app.domains.memory.exceptions import MemoryConflictError
    with pytest.raises(MemoryConflictError,match="revision_conflict"):
        service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,
            mode="regenerate_failed",expected_revision=0)


def test_cancel_during_provider_fences_late_result_and_resume_keeps_same_work(memory_session,monkeypatch):
    from app.domains.relationships.service.daily_review import run_review_step
    from test_relationship_daily_review import References
    db=memory_session
    scope,_,workflows,data=setup(db)
    memories(db,scope,monkeypatch)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data)
    finish_memory(db,result["request_id"])
    advance_manual_requests(db,datetime.now(UTC));db.commit()
    request=db.get(RelationshipReviewRequest,result["request_id"])
    identifier=request.work_ids[0]
    calls=[]
    class CancelProvider:
        async def review(self,payload,**kwargs):
            calls.append(1)
            closed=service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,
                mode="cancel_remaining",expected_revision=0)["progress"]
            assert closed["flow_state"]=="cancelled"
            return {"decision":"keep","memory_refs":[]}
    outcome=asyncio.run(run_review_step(sessionmaker(db.bind,expire_on_commit=False),work_id=identifier,
        references_factory=lambda session:References(),provider_factory=lambda base:CancelProvider(),received={}))
    assert outcome=="lease_lost" and calls==[1]
    db.expire_all()
    row=db.get(RelationshipReviewWork,identifier)
    assert row.status=="failed" and row.result is None and row.maintenance["hold"]=="cancelled"
    service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,
        mode="resume_remaining",expected_revision=1)
    assert db.get(RelationshipReviewWork,identifier).status=="pending"
    assert request.work_ids==[identifier]


def test_cancel_resume_preserves_ready_result_instead_of_regenerating(memory_session,monkeypatch):
    db=memory_session
    scope,_,workflows,data=setup(db)
    memories(db,scope,monkeypatch)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data)
    finish_memory(db,result["request_id"])
    advance_manual_requests(db,datetime.now(UTC));db.commit()
    request=db.get(RelationshipReviewRequest,result["request_id"])
    row=db.get(RelationshipReviewWork,request.work_ids[0])
    saved={"decision":"keep","memory_refs":[]}
    row.status,row.result="ready",saved;db.commit()
    service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,mode="cancel_remaining",expected_revision=0)
    service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,mode="resume_remaining",expected_revision=1)
    assert row.status=="ready" and row.result==saved


def test_split_storage_recovery_restores_received_child_and_unclaimed_root(memory_session,monkeypatch):
    from app.domains.relationships.service.review_payloads import new_work
    from app.domains.relationships.service.review_recovery import fail
    db=memory_session
    scope,_,workflows,data=setup(db)
    memories(db,scope,monkeypatch)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data)
    finish_memory(db,result["request_id"])
    advance_manual_requests(db,datetime.now(UTC));db.commit()
    request=db.get(RelationshipReviewRequest,result["request_id"])
    root=db.get(RelationshipReviewWork,request.work_ids[0]);root.phase="final"
    child=new_work(db,world_id=root.world_id,actor_id=root.actor_world_character_id,target_id=root.target_world_character_id,
        period_key=root.period_key,part_key="storage-child",phase="partial",manifest=root.manifest,
        view_version=root.expected_view_version,parent_id=root.id)
    child.status,child.lease_token,child.attempts="running","received-token",1
    child.maintenance={"storage_rounds":3,"received_lease":"received-token"}
    fail(db,child,"relationship_storage_retry_exhausted",now=datetime.now(UTC))
    request.state="partial_failed";db.commit()
    value=service.read(scope=scope,db=db,workflows=workflows)["progress"]
    assert "resume_storage" in value["actions"] and "regenerate_failed" not in value["actions"]
    service.retry(scope=scope,db=db,workflows=workflows,request_id=result["request_id"],key=uuid4().hex,mode="resume_storage",expected_revision=0)
    assert root.status=="pending" and root.lease_token is None
    assert child.status=="running" and child.lease_token=="received-token" and child.attempts==1
