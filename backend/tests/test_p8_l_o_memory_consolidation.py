from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.identity.public import CredentialMaterial, CredentialPurpose
from app.domains.memory.infrastructure import (
    SqlAlchemyMemoryConsolidationRepository,
    SqlAlchemyMemoryMaintenanceQueue,
    SqlAlchemyMemoryMaintenanceUnitOfWork,
)
from app.domains.memory.public import (
    CanonicalMemoryEvidence,
    MemoryCandidateStatus,
    MemoryConflictError,
    MemoryConsolidationOutcome,
    MemoryConsolidationProviderError,
    MemoryConsolidationProviderResult,
    MemoryConsolidationService,
    MemoryHotBriefStatus,
    MemoryKindV1,
    MemoryMaintenanceLane,
    MemoryProviderMode,
    MemoryScope,
    MemoryScopeService,
    MemorySourceTypeV1,
    MemorySummaryProposal,
    MemoryWriteLifecycleService,
    parse_memory_consolidation_payload,
)
from app.providers.contracts import ProviderResponse, ProviderUsage
import app.integrations.llm.memory_consolidation as consolidation_adapter_module
from app.integrations.llm.memory_consolidation import (
    DirectLlmMemoryConsolidationProvider,
)


NOW = datetime(2026, 9, 2, 9, tzinfo=UTC)


class FakeSourceReader:
    def __init__(self) -> None:
        self.values: dict[
            tuple[MemorySourceTypeV1, str], CanonicalMemoryEvidence
        ] = {}

    def read_evidence(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        del scope
        return self.values.get((source_type, source_id))


class FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests = []

    async def consolidate(self, request):
        self.requests.append(request)
        if self.fail:
            raise MemoryConsolidationProviderError(
                "memory_maintenance_provider_timeout",
                physical_call_count=1,
            )
        return MemoryConsolidationProviderResult(
            proposals=tuple(
                MemorySummaryProposal(
                    candidate_ref=source.candidate_ref,
                    summary=f"압축됨: {source.deterministic_summary}",
                )
                for source in request.sources
            ),
            provider="fixture",
            model="fixture-model",
            physical_call_count=1,
        )


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_world(session: Session) -> MemoryScope:
    owner = models.User(
        id="consolidation-owner",
        email="consolidation-owner@example.test",
        display_name="Consolidation Owner",
        profile_setup_completed=True,
    )
    subject_character = _character("consolidation-subject-character", owner.id, "subject")
    counterpart_character = _character(
        "consolidation-counterpart-character", owner.id, "counterpart"
    )
    world = models.World(
        id="consolidation-world",
        slug="consolidation-world",
        owner_user_id=owner.id,
        name="Consolidation World",
        tagline="",
        setting_description="",
        daily_life_description="",
        genre_tags=[],
        tone_tags=[],
        timezone="Asia/Seoul",
        language="ko",
        visibility="private",
        join_policy="private",
        status="published",
        contract_version="world-v1",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="consolidation-world",
    )
    membership = models.WorldMembership(
        id="consolidation-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=NOW,
    )
    subject = _world_character(
        "consolidation-subject",
        world.id,
        subject_character.id,
        membership.id,
    )
    counterpart = _world_character(
        "consolidation-counterpart",
        world.id,
        counterpart_character.id,
        membership.id,
    )
    session.add_all([owner, subject_character, counterpart_character, world])
    session.flush()
    session.add(membership)
    session.flush()
    session.add_all([subject, counterpart])
    session.commit()
    return MemoryScope(
        owner_id=owner.id,
        world_id=world.id,
        subject_world_character_id=subject.id,
    )


def _character(identifier: str, owner_id: str, handle: str) -> models.Character:
    return models.Character(
        id=identifier,
        owner_id=owner_id,
        name=handle.title(),
        handle=handle,
        one_liner="",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="memory",
        safety_rules="safe",
        status="inactive",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


def _world_character(
    identifier: str,
    world_id: str,
    character_id: str,
    membership_id: str,
) -> models.WorldCharacter:
    return models.WorldCharacter(
        id=identifier,
        world_id=world_id,
        character_id=character_id,
        membership_id=membership_id,
        role_key="no_specific_role",
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
        world_contract_hash="a" * 64,
        version=1,
    )


def _evidence(
    scope: MemoryScope,
    source_id: str,
    *,
    visible: bool = True,
) -> CanonicalMemoryEvidence:
    summary = f"{source_id}에서 함께 훈련하고 서로를 격려했다."
    return CanonicalMemoryEvidence(
        source_type=MemorySourceTypeV1.POST,
        source_id=source_id,
        source_world_id=scope.world_id,
        source_digest=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        source_created_at=NOW,
        deterministic_summary=summary,
        successful=True,
        visible=visible,
        observed_by_subject=True,
        membership_active=True,
        blocked=False,
        actor_world_character_id=scope.subject_world_character_id,
        target_world_character_id=None,
        observation_id=None,
        source_event_id=f"event-{source_id}",
        counterpart_world_character_id=None,
        thread_id=None,
    )


def _stack(
    session: Session,
    *,
    provider_mode: MemoryProviderMode = MemoryProviderMode.NONE,
    provider: FakeProvider | None = None,
):
    scope = _seed_world(session)
    reader = FakeSourceReader()
    repository = SqlAlchemyMemoryConsolidationRepository(session)
    initial = MemoryScopeService(repository).get_or_create(scope)
    setting = MemoryScopeService(repository).update(
        scope,
        expected_version=initial.version,
        enabled=True,
        retention_days=180,
        provider_mode=provider_mode,
    )
    session.commit()
    writer = MemoryWriteLifecycleService(repository, reader)
    service = MemoryConsolidationService(
        repository=repository,
        queue=SqlAlchemyMemoryMaintenanceQueue(session),
        unit_of_work=SqlAlchemyMemoryMaintenanceUnitOfWork(session),
        source_reader=reader,
        write_lifecycle=writer,
        provider=provider,
        clock=lambda: NOW,
    )
    return scope, setting, reader, repository, writer, service


def _propose(
    writer: MemoryWriteLifecycleService,
    reader: FakeSourceReader,
    scope: MemoryScope,
    count: int,
) -> None:
    for index in range(count):
        source_id = f"post-{index + 1}"
        reader.values[(MemorySourceTypeV1.POST, source_id)] = _evidence(
            scope,
            source_id,
        )
        result = writer.propose_candidate(
            scope=scope,
            source_type=MemorySourceTypeV1.POST,
            source_id=source_id,
            memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
        )
        assert result.provider_call_count == 0


def test_automatic_threshold_keeps_ordinary_sources_provider_free(
    memory_session: Session,
) -> None:
    provider = FakeProvider()
    scope, setting, reader, _repository, writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    _propose(writer, reader, scope, 7)
    memory_session.commit()

    result = service.schedule_if_due(scope_setting_id=setting.id, now=NOW)

    assert result.outcome is MemoryConsolidationOutcome.NOT_DUE
    assert result.provider_call_count == 0
    assert provider.requests == []
    assert memory_session.query(models.MemoryMaintenanceJob).count() == 0


def test_threshold_batch_accepts_deterministically_and_builds_hot_brief(
    memory_session: Session,
) -> None:
    scope, setting, reader, _repository, writer, service = _stack(memory_session)
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    scheduled = service.schedule_if_due(scope_setting_id=setting.id, now=NOW)
    replay = service.schedule_if_due(scope_setting_id=setting.id, now=NOW)

    result = asyncio.run(service.run_next(lease_token="worker-threshold"))

    assert scheduled.outcome is MemoryConsolidationOutcome.ENQUEUED
    assert replay.job_id == scheduled.job_id
    assert result.outcome is MemoryConsolidationOutcome.COMPLETED
    assert result.provider_call_count == 0
    assert len(result.accepted_item_ids) == 8
    assert result.hot_brief is not None
    assert result.hot_brief.generation == 1
    assert len(result.hot_brief.source_items) == 8
    assert memory_session.query(models.MemoryItem).count() == 8
    assert memory_session.query(models.MemoryItemEvidence).count() == 8
    assert all(
        row.status == MemoryCandidateStatus.ACCEPTED.value
        for row in memory_session.query(models.MemoryCandidate).all()
    )


def test_bounded_batch_enqueues_and_drains_sub_threshold_continuation(
    memory_session: Session,
) -> None:
    scope, setting, reader, _repository, writer, service = _stack(memory_session)
    _propose(writer, reader, scope, 33)
    memory_session.commit()
    service.schedule_if_due(scope_setting_id=setting.id, now=NOW)

    first = asyncio.run(service.run_next(lease_token="worker-batch-1"))
    second = asyncio.run(service.run_next(lease_token="worker-batch-2"))

    assert len(first.accepted_item_ids) == 32
    assert first.continuation_job_id is not None
    assert len(second.accepted_item_ids) == 1
    assert second.continuation_job_id is None
    assert memory_session.query(models.MemoryCandidate).filter_by(
        status=MemoryCandidateStatus.PENDING.value
    ).count() == 0
    assert memory_session.query(models.MemoryItem).count() == 33


def test_optional_provider_uses_one_separate_batch_call(
    memory_session: Session,
) -> None:
    provider = FakeProvider()
    scope, setting, reader, _repository, writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    service.schedule_if_due(scope_setting_id=setting.id, now=NOW)

    result = asyncio.run(service.run_next(lease_token="worker-provider"))

    assert result.outcome is MemoryConsolidationOutcome.COMPLETED
    assert result.provider_call_count == 1
    assert result.provider_telemetry is not None
    assert result.provider_telemetry.provider == "fixture"
    assert len(provider.requests) == 1
    assert provider.requests[0].lane is MemoryMaintenanceLane.AUTOMATIC
    summaries = [row.summary for row in memory_session.query(models.MemoryItem).all()]
    assert all(summary.startswith("압축됨:") for summary in summaries)


def test_explicit_request_has_independent_immediate_budget(
    memory_session: Session,
) -> None:
    provider = FakeProvider()
    scope, setting, reader, _repository, writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    _propose(writer, reader, scope, 1)
    memory_session.commit()

    scheduled = service.schedule_immediate(
        scope_setting_id=setting.id,
        request_key="user-message-1",
        now=NOW,
    )
    result = asyncio.run(service.run_next(lease_token="worker-immediate"))

    assert scheduled.outcome is MemoryConsolidationOutcome.ENQUEUED
    assert result.lane is MemoryMaintenanceLane.IMMEDIATE
    assert result.provider_call_count == 1
    assert provider.requests[0].lane is MemoryMaintenanceLane.IMMEDIATE


def test_provider_failure_preserves_canonical_items_and_basic_brief(
    memory_session: Session,
) -> None:
    provider = FakeProvider(fail=True)
    scope, setting, reader, _repository, writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    service.schedule_if_due(scope_setting_id=setting.id, now=NOW)

    result = asyncio.run(service.run_next(lease_token="worker-fallback"))

    assert result.outcome is MemoryConsolidationOutcome.DEGRADED
    assert result.provider_call_count == 1
    assert result.provider_failure_code == "memory_maintenance_provider_timeout"
    assert len(result.accepted_item_ids) == 8
    assert result.hot_brief is not None
    assert memory_session.query(models.MemoryItem).count() == 8
    assert all(
        not row.summary.startswith("압축됨:")
        for row in memory_session.query(models.MemoryItem).all()
    )


def test_off_scope_never_invokes_provider_or_processes_candidates(
    memory_session: Session,
) -> None:
    provider = FakeProvider()
    scope, setting, _reader, repository, _writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    disabled = MemoryScopeService(repository).update(
        scope,
        expected_version=setting.version,
        enabled=False,
        retention_days=180,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
    )
    memory_session.commit()
    not_due = service.schedule_if_due(scope_setting_id=disabled.id, now=NOW)
    queue = SqlAlchemyMemoryMaintenanceQueue(memory_session)
    queue.enqueue(
        scope_setting_id=disabled.id,
        reason="hot_brief_refresh",
        idempotency_key="off-scope-job",
    )
    memory_session.commit()

    result = asyncio.run(service.run_next(lease_token="worker-off"))

    assert not_due.outcome is MemoryConsolidationOutcome.NOT_DUE
    assert result.outcome is MemoryConsolidationOutcome.SKIPPED
    assert result.code == "memory_opt_out"
    assert result.provider_call_count == 0
    assert provider.requests == []


def test_source_is_revalidated_before_provider_and_rejected(
    memory_session: Session,
) -> None:
    provider = FakeProvider()
    scope, setting, reader, _repository, writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    service.schedule_if_due(scope_setting_id=setting.id, now=NOW)
    for index in range(8):
        source_id = f"post-{index + 1}"
        reader.values[(MemorySourceTypeV1.POST, source_id)] = _evidence(
            scope,
            source_id,
            visible=False,
        )

    result = asyncio.run(service.run_next(lease_token="worker-revalidate"))

    assert result.outcome is MemoryConsolidationOutcome.COMPLETED
    assert len(result.rejected_candidate_ids) == 8
    assert result.provider_call_count == 0
    assert provider.requests == []
    assert memory_session.query(models.MemoryItem).count() == 0


def test_source_digest_drift_is_rejected_before_optional_provider(
    memory_session: Session,
) -> None:
    provider = FakeProvider()
    scope, setting, reader, _repository, writer, service = _stack(
        memory_session,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
        provider=provider,
    )
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    service.schedule_if_due(scope_setting_id=setting.id, now=NOW)
    for index in range(8):
        source_id = f"post-{index + 1}"
        changed = _evidence(scope, source_id)
        reader.values[(MemorySourceTypeV1.POST, source_id)] = CanonicalMemoryEvidence(
            source_type=changed.source_type,
            source_id=changed.source_id,
            source_world_id=changed.source_world_id,
            source_digest="f" * 64,
            source_created_at=changed.source_created_at,
            deterministic_summary=changed.deterministic_summary,
            successful=changed.successful,
            visible=changed.visible,
            observed_by_subject=changed.observed_by_subject,
            membership_active=changed.membership_active,
            blocked=changed.blocked,
            actor_world_character_id=changed.actor_world_character_id,
            target_world_character_id=changed.target_world_character_id,
            observation_id=changed.observation_id,
            source_event_id=changed.source_event_id,
            counterpart_world_character_id=changed.counterpart_world_character_id,
            thread_id=changed.thread_id,
        )

    result = asyncio.run(service.run_next(lease_token="worker-digest-drift"))

    assert result.outcome is MemoryConsolidationOutcome.COMPLETED
    assert len(result.rejected_candidate_ids) == 8
    assert result.provider_call_count == 0
    assert provider.requests == []
    assert {
        row.reason_code
        for row in memory_session.query(models.MemoryCandidate).all()
    } == {"memory_source_digest_conflict"}


def test_hot_brief_rebuilds_generation_after_source_set_change(
    memory_session: Session,
) -> None:
    scope, setting, reader, _repository, writer, service = _stack(memory_session)
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    service.schedule_if_due(scope_setting_id=setting.id, now=NOW)
    first = asyncio.run(service.run_next(lease_token="worker-brief-1"))
    reader.values[(MemorySourceTypeV1.POST, "post-9")] = _evidence(scope, "post-9")
    writer.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="post-9",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    memory_session.commit()
    service.schedule_immediate(
        scope_setting_id=setting.id,
        request_key="brief-rebuild",
        now=NOW,
    )

    second = asyncio.run(service.run_next(lease_token="worker-brief-2"))

    assert first.hot_brief is not None and first.hot_brief.generation == 1
    assert second.hot_brief is not None and second.hot_brief.generation == 2
    first_row = memory_session.get(models.MemoryHotBrief, first.hot_brief.id)
    assert first_row is not None
    assert first_row.status == MemoryHotBriefStatus.INVALIDATED.value
    MemoryScopeService(_repository).update(
        scope,
        expected_version=setting.version,
        enabled=False,
        retention_days=180,
    )
    memory_session.flush()
    second_row = memory_session.get(models.MemoryHotBrief, second.hot_brief.id)
    assert second_row is not None
    assert second_row.status == MemoryHotBriefStatus.INVALIDATED.value


def test_hot_brief_replace_fences_exact_item_versions(memory_session: Session) -> None:
    scope, setting, reader, repository, writer, _service = _stack(memory_session)
    _propose(writer, reader, scope, 1)
    candidate = memory_session.query(models.MemoryCandidate).one()
    writer.accept_candidate(
        scope=scope,
        candidate_id=candidate.id,
        expected_candidate_version=candidate.version,
        expected_scope_version=setting.version,
        enqueue_maintenance=False,
        now=NOW,
    )
    memory_session.flush()
    sources = repository.hot_brief_source_items(
        setting=setting,
        now=NOW,
        limit=24,
    )
    row = memory_session.get(models.MemoryItem, sources[0].id)
    assert row is not None
    row.version += 1
    memory_session.flush()

    with pytest.raises(MemoryConflictError, match="source_version_conflict"):
        repository.replace_hot_brief(
            setting=setting,
            expected_source_items=sources,
            summary="brief",
            contract_version="memory-hot-brief.v1",
            now=NOW,
        )


def test_worker_retry_is_bounded_to_three_claims(
    memory_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope, setting, reader, repository, writer, service = _stack(memory_session)
    _propose(writer, reader, scope, 8)
    memory_session.commit()
    scheduled = service.schedule_if_due(scope_setting_id=setting.id, now=NOW)

    def _fail_replace(**_kwargs):
        raise MemoryConflictError("memory_hot_brief_fixture_failure")

    monkeypatch.setattr(repository, "replace_hot_brief", _fail_replace)
    first = asyncio.run(service.run_next(lease_token="worker-retry-1"))
    second = asyncio.run(service.run_next(lease_token="worker-retry-2"))
    third = asyncio.run(service.run_next(lease_token="worker-retry-3"))

    assert first.outcome is MemoryConsolidationOutcome.RETRY_SCHEDULED
    assert second.outcome is MemoryConsolidationOutcome.RETRY_SCHEDULED
    assert third.outcome is MemoryConsolidationOutcome.FAILED
    row = memory_session.get(models.MemoryMaintenanceJob, scheduled.job_id)
    assert row is not None and row.attempt_count == 3
    assert row.status == "failed"
    # Each accepted item + evidence pair is independently atomic and replay
    # safe.  A later derived-brief failure never deletes canonical items.
    assert memory_session.query(models.MemoryItem).count() == 8
    assert memory_session.query(models.MemoryItemEvidence).count() == 8
    assert memory_session.query(models.MemoryHotBrief).count() == 0


def test_shutdown_drain_obeys_deadline_and_job_cap(memory_session: Session) -> None:
    _scope, setting, _reader, _repository, _writer, service = _stack(memory_session)
    queue = SqlAlchemyMemoryMaintenanceQueue(memory_session)
    for index in range(2):
        queue.enqueue(
            scope_setting_id=setting.id,
            reason="hot_brief_refresh",
            idempotency_key=f"drain-{index}",
        )
    memory_session.commit()

    results = asyncio.run(
        service.drain(
            lease_token_prefix="shutdown",
            deadline=NOW + timedelta(seconds=1),
            max_jobs=1,
        )
    )
    expired = asyncio.run(
        service.drain(
            lease_token_prefix="expired",
            deadline=NOW,
            max_jobs=1,
        )
    )

    assert len(results) == 1
    assert expired == ()
    assert memory_session.query(models.MemoryMaintenanceJob).filter_by(status="pending").count() == 1


def test_provider_output_contract_rejects_unknown_shape_and_duplicates() -> None:
    assert parse_memory_consolidation_payload(
        {
            "version": "memory-consolidation-output.v1",
            "proposals": [
                {"candidate_ref": "candidate-1", "summary": "함께 훈련했다."}
            ],
        }
    )[0].candidate_ref == "candidate-1"
    with pytest.raises(Exception, match="shape_invalid"):
        parse_memory_consolidation_payload(
            {
                "version": "memory-consolidation-output.v1",
                "proposals": [],
                "extra": True,
            }
        )
    with pytest.raises(Exception, match="proposal_invalid"):
        parse_memory_consolidation_payload(
            {
                "version": "memory-consolidation-output.v1",
                "proposals": [
                    {"candidate_ref": "candidate-1", "summary": "첫째"},
                    {"candidate_ref": "candidate-1", "summary": "둘째"},
                ],
            }
        )


def test_direct_adapter_uses_one_transport_attempt_without_generic_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class FakeAdapter:
        async def generate_json(self, request):
            captured["requests"] = captured.get("requests", 0) + 1
            captured["request"] = request
            return ProviderResponse(
                text="",
                parsed={
                    "version": "memory-consolidation-output.v1",
                    "proposals": [
                        {
                            "candidate_ref": "candidate-1",
                            "summary": "간결한 기억",
                        }
                    ],
                },
                usage=ProviderUsage(
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                ),
            )

    monkeypatch.setattr(
        consolidation_adapter_module,
        "get_provider_adapter",
        lambda _provider, _model: FakeAdapter(),
    )
    adapter = DirectLlmMemoryConsolidationProvider(
        CredentialMaterial(
            credential_id="credential-1",
            provider="google",
            model="fixture-model",
            fingerprint="fixture-fingerprint",
            purpose=CredentialPurpose.MESSAGE_LLM,
            _secret="fixture-secret",
        )
    )
    result = asyncio.run(
        adapter.consolidate(
            type(
            "Request",
            (),
            {
                "batch_ref": "batch-1",
                "lane": MemoryMaintenanceLane.AUTOMATIC,
                "sources": (
                    type(
                        "Source",
                        (),
                        {
                            "candidate_ref": "candidate-1",
                            "memory_kind": "AUTOBIOGRAPHICAL_EVENT",
                            "deterministic_summary": "함께 훈련했다.",
                        },
                    )(),
                ),
            },
            )()
        )
    )

    assert result.physical_call_count == 1
    assert result.total_token_count == 15
    assert captured["requests"] == 1
    assert captured["request"].response_mime_type == "application/json"
