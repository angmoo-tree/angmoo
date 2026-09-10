"""Deterministic provider-call and preservation checks; no real API credentials."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.models.batch import MemoryBatchRun, MemoryActivationEpoch
from app.domains.memory.models.items import MemoryMaintenanceJob
from app.domains.memory.policies.batch import MAX_SELECTION_OUTPUT_TOKENS
from app.domains.memory.policies.selection_output import MemorySelectionSource
from app.integrations.llm import memory_selection
from app.providers.generation_profiles import GENERATION_MODELS, THINKING_LEVELS
from app.runtime.memory.batch_runtime import MemoryBatchRuntime
from app.runtime.memory.composition import memory_batch_repository
from app.runtime.memory.source_delivery import install_memory_delivery, uninstall_memory_delivery
from memory.test_p8_l_o_memory_consolidation import memory_session, _stack
from memory.test_p8_l_r_memory_batch_safety import _post, _save
from memory.test_p8_l_r_memory_batch_runtime import Selector


@pytest.mark.parametrize("count", [0, 1, 8, 13, 31, 32, 33, 64, 65])
def test_compatible_experiences_are_one_call_per_32(memory_session, count):
    scope, *_ = _stack(memory_session)
    memory_session.scalar(select(MemoryActivationEpoch)).opened_at = datetime.now(UTC) - timedelta(minutes=1)
    _save(memory_batch_repository(memory_session), scope)
    memory_session.commit()
    factory = sessionmaker(bind=memory_session.bind)
    sizes = []

    class BatchSelector(Selector):
        async def select(self, sources, *, timeout):
            sizes.append(len(sources))
            return await super().select(sources, timeout=timeout)

    selector = BatchSelector(skip=True)
    runtime = MemoryBatchRuntime(factory, lambda owner, model, thinking: selector)
    install_memory_delivery(factory)
    try:
        for index in range(count):
            _post(memory_session, scope, f"batch32-source-{index}")
        for _ in range(4):
            asyncio.run(runtime.tick(shutdown=True))
        assert sizes == [32] * (count // 32) + ([count % 32] if count % 32 else [])
        assert selector.calls == (count + 31) // 32
        assert all(row.status == "succeeded" for row in memory_session.scalars(select(MemoryMaintenanceJob)))
    finally:
        uninstall_memory_delivery(factory)


@pytest.mark.parametrize("model", GENERATION_MODELS)
@pytest.mark.parametrize("thinking", THINKING_LEVELS)
def test_all_four_profiles_send_32_ids_once_and_keep_max_output(monkeypatch, model, thinking):
    requests = []

    class Adapter:
        async def generate_json(self, request):
            requests.append(request)
            sources = json.loads(request.user_prompt)["sources"]
            return SimpleNamespace(finish_reason="STOP", usage=None, parsed={
                "version": "memory-selection.v2", "batch_ref": "batch-1",
                "decisions": [{"candidate_ref": source["candidate_ref"], "decision": "skip",
                               "reason_code": "routine_low_salience", "memory": None} for source in sources],
            })

    monkeypatch.setattr(memory_selection, "get_provider_adapter", lambda *args: Adapter())
    material = CredentialMaterial("fixture", "google", model, None, CredentialPurpose.MESSAGE_LLM, "fixture-key", thinking)
    provider = memory_selection.DirectLlmMemorySelectionProvider(material)
    sources = tuple(MemorySelectionSource(f"candidate-{i}", f"source-{i}", "AUTOBIOGRAPHICAL_EVENT", "별개의 훈련 경험 " * 100, "본인이 기록한 감정 " * 20) for i in range(32))
    result = asyncio.run(provider.select(sources, timeout=180))
    assert len(result) == 32 and len(requests) == 1
    assert requests[0].model == model and requests[0].thinking_level == thinking
    assert requests[0].max_output_tokens == MAX_SELECTION_OUTPUT_TOKENS == 65_536


def test_released_v9_and_clean_v10_match_upgrade():
    from app.runtime.persistence.sqlite_schema import build_sqlite_v9_metadata, build_sqlite_v10_metadata, create_schema_version_table, sqlite_schema_contract_digest
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
    from app.runtime.migrations.sqlite_versions.v9_to_v10_generation_profiles import capture_v9_to_v10_delta, upgrade_v9_to_v10, verify_v9_to_v10_delta
    with create_engine("sqlite://").begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v9_metadata().create_all(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(9).schema_digest
        before = capture_v9_to_v10_delta(connection)
        upgrade_v9_to_v10(connection)
        verify_v9_to_v10_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(10).schema_digest
    with create_engine("sqlite://").begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v10_metadata().create_all(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(10).schema_digest


def test_explicit_retry_regroups_six_failed_pairs_without_duplicating_saved_item(memory_session):
    from app.domains.memory.models.batch import MemoryBatchSetting, MemorySourceDelivery
    from app.domains.memory.models.items import MemoryItem
    from sqlalchemy import func

    scope, setting, *_ = _stack(memory_session)
    memory_session.scalar(select(MemoryActivationEpoch)).opened_at = datetime.now(UTC) - timedelta(minutes=1)
    repo = memory_batch_repository(memory_session)
    _save(repo, scope)
    memory_session.commit()
    factory = sessionmaker(bind=memory_session.bind)
    sizes = []

    class RecordingSelector(Selector):
        async def select(self, sources, *, timeout):
            sizes.append(len(sources))
            return await super().select(sources, timeout=timeout)

    runtime = MemoryBatchRuntime(factory, lambda owner, model, thinking: RecordingSelector())
    install_memory_delivery(factory)
    try:
        _post(memory_session, scope, "already-retained")
        assert asyncio.run(runtime.tick(shutdown=True)) == "memory_selection_completed"
        saved_id = memory_session.scalar(select(MemoryItem.id))
        config = memory_session.get(MemoryBatchSetting, setting.id)
        config.trigger_kind = None
        config.trigger_cutoff = 0
        config.trigger_requested_at = None
        memory_session.commit()
        for index in range(12):
            _post(memory_session, scope, f"old-failed-{index}")
        runtime.prepare()
        memory_session.expire_all()
        deliveries = memory_session.scalars(select(MemorySourceDelivery).where(
            MemorySourceDelivery.batch_job_id.is_(None)).order_by(MemorySourceDelivery.sequence)).all()
        assert len(deliveries) == 12
        cutoff = max(row.sequence for row in deliveries)
        old_jobs = []
        for index in range(0, 12, 2):
            job_id = repo.enqueue(scope_setting_id=setting.id,
                candidate_ids=tuple(row.candidate_id for row in deliveries[index:index + 2]),
                cutoff=cutoff, trigger="scheduled", now=datetime.now(UTC))
            old_jobs.append(job_id)
            run = memory_session.get(MemoryBatchRun, job_id)
            run.policy_version, run.physical_calls = "memory-batch.v2", 3
            job = memory_session.get(MemoryMaintenanceJob, job_id)
            job.status, job.attempt_count = "failed", 3
            job.completed_at = datetime.now(UTC)
        memory_session.commit()
        repo.retry_failed(scope, idempotency_key="regroup-twelve", now=datetime.now(UTC))
        memory_session.commit()
        assert asyncio.run(runtime.tick()) == "memory_selection_completed"
        memory_session.expire_all()
        assert sizes == [1, 12]
        assert memory_session.get(MemoryItem, saved_id) is not None
        assert memory_session.scalar(select(func.count()).select_from(MemoryItem)) == 13
        for job_id in old_jobs:
            assert memory_session.get(MemoryBatchRun, job_id).physical_calls == 3
            assert memory_session.get(MemoryMaintenanceJob, job_id).status == "failed"
    finally:
        uninstall_memory_delivery(factory)
