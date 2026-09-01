from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.memory.infrastructure import (
    SqlAlchemyMemoryMaintenanceQueue,
    SqlAlchemyMemoryRepository,
    SqlAlchemyMemorySourceEvidenceReader,
)
from app.domains.memory.public import (
    CanonicalMemoryEvidence,
    MemoryCandidateStatus,
    MemoryConflictError,
    MemoryItemStatus,
    MemoryKindV1,
    MemoryNotFoundError,
    MemoryScope,
    MemoryScopeService,
    MemorySourceTypeV1,
    MemoryValidationError,
    MemoryWriteLifecycleService,
    MemoryWriteOutcome,
)


NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)
FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "core_experience" / "p0-contract-v1"
)


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


def _seed_world(session: Session) -> tuple[MemoryScope, str]:
    owner = models.User(
        id="memory-owner",
        email="memory-owner@example.test",
        display_name="Memory Owner",
        profile_setup_completed=True,
    )
    subject_character = _character("subject-character", owner.id, "subject")
    counterpart_character = _character("counterpart-character", owner.id, "counterpart")
    world = models.World(
        id="memory-world",
        slug="memory-world",
        owner_user_id=owner.id,
        name="Memory World",
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
        create_idempotency_key="memory-world",
    )
    membership = models.WorldMembership(
        id="memory-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=NOW,
    )
    subject = _world_character(
        "memory-subject",
        world.id,
        subject_character.id,
        membership.id,
    )
    counterpart = _world_character(
        "memory-counterpart",
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
    return (
        MemoryScope(
            owner_id=owner.id,
            world_id=world.id,
            subject_world_character_id=subject.id,
        ),
        counterpart.id,
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
    *,
    scope: MemoryScope,
    source_id: str,
    source_type: MemorySourceTypeV1 = MemorySourceTypeV1.POST,
    summary: str = "함께 훈련을 마치고 서로를 격려했다.",
    counterpart: str | None = None,
    thread_id: str | None = None,
    observation_id: str | None = None,
    successful: bool = True,
    visible: bool = True,
    observed: bool = True,
    membership_active: bool = True,
    blocked: bool = False,
    world_id: str | None = None,
) -> CanonicalMemoryEvidence:
    return CanonicalMemoryEvidence(
        source_type=source_type,
        source_id=source_id,
        source_world_id=world_id or scope.world_id,
        source_digest=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        source_created_at=NOW,
        deterministic_summary=summary,
        successful=successful,
        visible=visible,
        observed_by_subject=observed,
        membership_active=membership_active,
        blocked=blocked,
        actor_world_character_id=scope.subject_world_character_id,
        target_world_character_id=counterpart,
        observation_id=observation_id,
        source_event_id=f"event-{source_id}",
        counterpart_world_character_id=counterpart,
        thread_id=thread_id,
    )


def _enabled_service(
    session: Session,
    scope: MemoryScope,
    reader: FakeSourceReader,
) -> tuple[MemoryWriteLifecycleService, SqlAlchemyMemoryRepository, int]:
    repository = SqlAlchemyMemoryRepository(session)
    scope_service = MemoryScopeService(repository)
    initial = scope_service.get_or_create(scope)
    enabled = scope_service.update(
        scope,
        expected_version=initial.version,
        enabled=True,
        retention_days=180,
    )
    session.commit()
    return MemoryWriteLifecycleService(repository, reader), repository, enabled.version


def _propose_and_accept(
    *,
    service: MemoryWriteLifecycleService,
    reader: FakeSourceReader,
    scope: MemoryScope,
    source_id: str,
    scope_version: int,
    source_type: MemorySourceTypeV1 = MemorySourceTypeV1.POST,
    kind: MemoryKindV1 = MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    summary: str = "함께 훈련을 마치고 서로를 격려했다.",
    counterpart: str | None = None,
):
    reader.values[(source_type, source_id)] = _evidence(
        scope=scope,
        source_id=source_id,
        source_type=source_type,
        summary=summary,
        counterpart=counterpart,
    )
    proposed = service.propose_candidate(
        scope=scope,
        source_type=source_type,
        source_id=source_id,
        memory_kind=kind,
    )
    assert proposed.candidate is not None
    return service.accept_candidate(
        scope=scope,
        candidate_id=proposed.candidate.id,
        expected_candidate_version=proposed.candidate.version,
        expected_scope_version=scope_version,
        now=NOW,
    )


def test_memory_opt_out_fixture_is_an_executable_zero_write_gate(
    memory_session: Session,
) -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "memory_opt_out_blocked.json").read_text(encoding="utf-8")
    )
    scope, _ = _seed_world(memory_session)
    repository = SqlAlchemyMemoryRepository(memory_session)
    MemoryScopeService(repository).get_or_create(scope)
    reader = FakeSourceReader()
    reader.values[(MemorySourceTypeV1.POST, "post-off")] = _evidence(
        scope=scope,
        source_id="post-off",
    )

    result = MemoryWriteLifecycleService(repository, reader).propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="post-off",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )

    assert result.outcome.value == fixture["expected"]["outcome"]
    assert result.outcome is MemoryWriteOutcome.REJECTED
    assert result.code == fixture["expected"]["code"]
    assert list(result.writes) == fixture["expected"]["writes"]
    assert result.provider_call_count == fixture["expected"]["provider_call_count"]
    assert memory_session.query(models.MemoryCandidate).count() == 0
    assert memory_session.query(models.MemoryItem).count() == 0
    assert memory_session.query(models.MemoryMaintenanceJob).count() == 0


def test_candidate_is_idempotent_and_atomic_acceptance_has_provenance(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, _, scope_version = _enabled_service(memory_session, scope, reader)
    reader.values[(MemorySourceTypeV1.POST, "post-1")] = _evidence(
        scope=scope,
        source_id="post-1",
    )

    first = service.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="post-1",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    replay = service.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="  post-1  ",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    assert first.outcome is MemoryWriteOutcome.CREATED
    assert replay.outcome is MemoryWriteOutcome.REUSED
    assert replay.candidate is not None and first.candidate is not None
    assert replay.candidate.id == first.candidate.id
    assert memory_session.query(models.MemoryCandidate).count() == 1

    accepted = service.accept_candidate(
        scope=scope,
        candidate_id=first.candidate.id,
        expected_candidate_version=first.candidate.version,
        expected_scope_version=scope_version,
        now=NOW,
    )
    memory_session.commit()
    assert accepted.outcome is MemoryWriteOutcome.ACCEPTED
    assert accepted.provider_call_count == 0
    assert accepted.item is not None
    assert accepted.item.summary == "함께 훈련을 마치고 서로를 격려했다."
    assert memory_session.query(models.MemoryItem).count() == 1
    assert memory_session.query(models.MemoryItemEvidence).count() == 1
    assert memory_session.query(models.MemoryMaintenanceJob).count() == 1

    replay_accept = service.accept_candidate(
        scope=scope,
        candidate_id=first.candidate.id,
        expected_candidate_version=first.candidate.version,
        expected_scope_version=scope_version,
        now=NOW,
    )
    assert replay_accept.outcome is MemoryWriteOutcome.REUSED
    assert replay_accept.item is not None
    assert replay_accept.item.id == accepted.item.id
    assert memory_session.query(models.MemoryItem).count() == 1


def test_item_and_evidence_rollback_together_on_provenance_failure(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, _, scope_version = _enabled_service(memory_session, scope, reader)
    reader.values[(MemorySourceTypeV1.POST, "bad-observation")] = _evidence(
        scope=scope,
        source_id="bad-observation",
        observation_id="missing-observation",
    )
    proposed = service.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="bad-observation",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    assert proposed.candidate is not None

    with pytest.raises(IntegrityError):
        service.accept_candidate(
            scope=scope,
            candidate_id=proposed.candidate.id,
            expected_candidate_version=proposed.candidate.version,
            expected_scope_version=scope_version,
            now=NOW,
        )

    memory_session.expire_all()
    stored = memory_session.get(models.MemoryCandidate, proposed.candidate.id)
    assert stored is not None and stored.status == "pending" and stored.version == 1
    assert memory_session.query(models.MemoryItem).count() == 0
    assert memory_session.query(models.MemoryItemEvidence).count() == 0
    assert memory_session.query(models.MemoryMaintenanceJob).count() == 0


def test_correction_supersedes_old_item_and_delete_fixture_blocks_retrieval(
    memory_session: Session,
) -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "memory_deleted_blocked.json").read_text(encoding="utf-8")
    )
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, repository, scope_version = _enabled_service(memory_session, scope, reader)
    accepted = _propose_and_accept(
        service=service,
        reader=reader,
        scope=scope,
        source_id="original",
        scope_version=scope_version,
    )
    assert accepted.item is not None

    reader.values[(MemorySourceTypeV1.POST, "correction")] = _evidence(
        scope=scope,
        source_id="correction",
        summary="실제로는 훈련을 취소하고 서로 사과했다.",
    )
    proposed = service.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="correction",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    assert proposed.candidate is not None
    corrected = service.correct_item(
        scope=scope,
        old_item_id=accepted.item.id,
        expected_item_version=accepted.item.version,
        candidate_id=proposed.candidate.id,
        expected_candidate_version=proposed.candidate.version,
        expected_scope_version=scope_version,
        now=NOW + timedelta(minutes=1),
    )
    assert corrected.item is not None
    old = repository.get_item(scope=scope, item_id=accepted.item.id)
    assert old.status is MemoryItemStatus.SUPERSEDED
    assert old.superseded_by_id == corrected.item.id
    with pytest.raises(MemoryNotFoundError, match=fixture["expected"]["code"]):
        service.get_retrievable_item(scope=scope, item_id=old.id, now=NOW)

    deleted = service.delete_item(
        scope=scope,
        item_id=corrected.item.id,
        expected_version=corrected.item.version,
        now=NOW + timedelta(minutes=2),
    )
    assert deleted.item is not None
    assert deleted.item.status is MemoryItemStatus.DELETED
    maintenance_count = memory_session.query(models.MemoryMaintenanceJob).count()
    replayed_delete = service.delete_item(
        scope=scope,
        item_id=corrected.item.id,
        expected_version=corrected.item.version,
        now=NOW + timedelta(minutes=3),
    )
    assert replayed_delete.outcome is MemoryWriteOutcome.REUSED
    assert replayed_delete.writes == ()
    assert memory_session.query(models.MemoryMaintenanceJob).count() == maintenance_count
    with pytest.raises(MemoryNotFoundError, match=fixture["expected"]["code"]):
        service.get_retrievable_item(
            scope=scope,
            item_id=corrected.item.id,
            now=NOW,
        )


def test_pin_bypasses_retention_then_unpin_enqueues_expiry_once(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, _, scope_version = _enabled_service(memory_session, scope, reader)
    accepted = _propose_and_accept(
        service=service,
        reader=reader,
        scope=scope,
        source_id="ttl",
        scope_version=scope_version,
    )
    assert accepted.item is not None
    pinned = service.set_pin(
        scope=scope,
        item_id=accepted.item.id,
        expected_version=accepted.item.version,
        pinned=True,
        now=NOW,
    )
    assert pinned.item is not None and pinned.item.pinned_at is not None
    pin_job_count = memory_session.query(models.MemoryMaintenanceJob).count()
    replayed_pin = service.set_pin(
        scope=scope,
        item_id=accepted.item.id,
        expected_version=accepted.item.version,
        pinned=True,
        now=NOW + timedelta(seconds=1),
    )
    assert replayed_pin.outcome is MemoryWriteOutcome.REUSED
    assert replayed_pin.writes == ()
    assert memory_session.query(models.MemoryMaintenanceJob).count() == pin_job_count
    future = NOW + timedelta(days=181)
    assert service.expire_due(scope=scope, now=future) == ()
    assert service.get_retrievable_item(
        scope=scope,
        item_id=accepted.item.id,
        now=future,
    ).id == accepted.item.id

    unpinned = service.set_pin(
        scope=scope,
        item_id=accepted.item.id,
        expected_version=pinned.item.version,
        pinned=False,
        now=NOW + timedelta(minutes=1),
    )
    assert unpinned.item is not None and unpinned.item.pinned_at is None
    expired = service.expire_due(scope=scope, now=future)
    assert len(expired) == 1
    assert service.expire_due(scope=scope, now=future) == ()
    with pytest.raises(MemoryNotFoundError, match="memory_not_retrievable"):
        service.get_retrievable_item(
            scope=scope,
            item_id=accepted.item.id,
            now=future,
        )


def test_expired_item_cannot_be_pinned_and_resurrected(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, repository, scope_version = _enabled_service(memory_session, scope, reader)
    accepted = _propose_and_accept(
        service=service,
        reader=reader,
        scope=scope,
        source_id="expired-before-pin",
        scope_version=scope_version,
    )
    assert accepted.item is not None
    future = NOW + timedelta(days=181)

    with pytest.raises(MemoryConflictError, match="memory_item_expired"):
        service.set_pin(
            scope=scope,
            item_id=accepted.item.id,
            expected_version=accepted.item.version,
            pinned=True,
            now=future,
        )

    unchanged = repository.get_item(scope=scope, item_id=accepted.item.id)
    assert unchanged.version == accepted.item.version
    assert unchanged.pinned_at is None
    with pytest.raises(MemoryNotFoundError, match="memory_not_retrievable"):
        service.get_retrievable_item(
            scope=scope,
            item_id=accepted.item.id,
            now=future,
        )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("successful", False, "memory_source_not_successful"),
        ("visible", False, "memory_source_not_visible"),
        ("observed", False, "memory_unobserved"),
        ("membership_active", False, "memory_membership_inactive"),
        ("blocked", True, "memory_blocked"),
        ("world_id", "other-world", "memory_world_mismatch"),
    ],
)
def test_eligibility_failures_leave_no_candidate_or_provider_call(
    memory_session: Session,
    field: str,
    value: object,
    code: str,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, _, _ = _enabled_service(memory_session, scope, reader)
    kwargs = {field: value}
    reader.values[(MemorySourceTypeV1.POST, "blocked-source")] = _evidence(
        scope=scope,
        source_id="blocked-source",
        **kwargs,
    )
    result = service.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="blocked-source",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    assert result.code == code
    assert result.writes == ()
    assert result.provider_call_count == 0
    assert memory_session.query(models.MemoryCandidate).count() == 0


def test_empty_canonical_summary_fails_closed_without_candidate(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, _, _ = _enabled_service(memory_session, scope, reader)
    reader.values[(MemorySourceTypeV1.POST, "empty-summary")] = _evidence(
        scope=scope,
        source_id="empty-summary",
        summary="   ",
    )

    with pytest.raises(MemoryValidationError, match="memory_summary_invalid"):
        service.propose_candidate(
            scope=scope,
            source_type=MemorySourceTypeV1.POST,
            source_id="empty-summary",
            memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
        )

    assert memory_session.query(models.MemoryCandidate).count() == 0


def test_stale_item_version_fails_without_mutation(memory_session: Session) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, repository, scope_version = _enabled_service(memory_session, scope, reader)
    accepted = _propose_and_accept(
        service=service,
        reader=reader,
        scope=scope,
        source_id="stale",
        scope_version=scope_version,
    )
    assert accepted.item is not None
    with pytest.raises(MemoryConflictError, match="version_conflict"):
        service.set_pin(
            scope=scope,
            item_id=accepted.item.id,
            expected_version=accepted.item.version + 1,
            pinned=True,
            now=NOW,
        )
    unchanged = repository.get_item(scope=scope, item_id=accepted.item.id)
    assert unchanged.version == accepted.item.version
    assert unchanged.pinned_at is None


def test_source_invalidation_tombstones_item_and_pending_candidate(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    reader = FakeSourceReader()
    service, repository, scope_version = _enabled_service(memory_session, scope, reader)
    accepted = _propose_and_accept(
        service=service,
        reader=reader,
        scope=scope,
        source_id="shared-source",
        scope_version=scope_version,
    )
    assert accepted.item is not None
    reader.values[(MemorySourceTypeV1.POST, "pending-source")] = _evidence(
        scope=scope,
        source_id="pending-source",
    )
    pending = service.propose_candidate(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="pending-source",
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
    )
    assert pending.candidate is not None
    assert pending.candidate.status is MemoryCandidateStatus.PENDING

    results = service.invalidate_source(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id="shared-source",
        now=NOW + timedelta(minutes=1),
    )
    assert len(results) == 1
    assert repository.get_item(
        scope=scope,
        item_id=accepted.item.id,
    ).status is MemoryItemStatus.DELETED
    with pytest.raises(MemoryNotFoundError, match="memory_not_retrievable"):
        service.get_retrievable_item(
            scope=scope,
            item_id=accepted.item.id,
            now=NOW,
        )
    maintenance_count = memory_session.query(models.MemoryMaintenanceJob).count()
    assert (
        service.invalidate_source(
            scope=scope,
            source_type=MemorySourceTypeV1.POST,
            source_id="shared-source",
            now=NOW + timedelta(minutes=2),
        )
        == ()
    )
    assert memory_session.query(models.MemoryMaintenanceJob).count() == maintenance_count

    assert (
        service.invalidate_source(
            scope=scope,
            source_type=MemorySourceTypeV1.POST,
            source_id="pending-source",
            now=NOW + timedelta(minutes=3),
        )
        == ()
    )
    rejected = repository.get_candidate(
        scope=scope,
        candidate_id=pending.candidate.id,
    )
    assert rejected.status is MemoryCandidateStatus.REJECTED
    assert rejected.reason_code == "memory_source_invalidated"


def test_maintenance_queue_serializes_same_scope_and_fences_completion(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    repository = SqlAlchemyMemoryRepository(memory_session)
    setting = MemoryScopeService(repository).get_or_create(scope)
    queue = SqlAlchemyMemoryMaintenanceQueue(memory_session)
    first_id = queue.enqueue(
        scope_setting_id=setting.id,
        reason="first",
        idempotency_key="first",
    )
    assert (
        queue.enqueue(
            scope_setting_id=setting.id,
            reason="first",
            idempotency_key="first",
        )
        == first_id
    )
    with pytest.raises(MemoryConflictError, match="replay_conflict"):
        queue.enqueue(
            scope_setting_id=setting.id,
            reason="different",
            idempotency_key="first",
        )
    second_id = queue.enqueue(
        scope_setting_id=setting.id,
        reason="second",
        idempotency_key="second",
    )
    first = queue.claim(
        lease_token="lease-1",
        now=NOW,
        lease_for=timedelta(minutes=5),
    )
    assert first is not None and first.job_id in {first_id, second_id}
    remaining_id = second_id if first.job_id == first_id else first_id
    assert (
        queue.claim(
            lease_token="lease-2",
            now=NOW,
            lease_for=timedelta(minutes=5),
        )
        is None
    )
    with pytest.raises(MemoryConflictError, match="lease_conflict"):
        queue.complete(job_id=first.job_id, lease_token="wrong", now=NOW)
    queue.complete(job_id=first.job_id, lease_token="lease-1", now=NOW)
    second = queue.claim(
        lease_token="lease-2",
        now=NOW,
        lease_for=timedelta(minutes=5),
    )
    assert second is not None and second.job_id == remaining_id


def test_expired_maintenance_lease_is_fenced_before_reclaim(
    memory_session: Session,
) -> None:
    scope, _ = _seed_world(memory_session)
    repository = SqlAlchemyMemoryRepository(memory_session)
    setting = MemoryScopeService(repository).get_or_create(scope)
    queue = SqlAlchemyMemoryMaintenanceQueue(memory_session)
    job_id = queue.enqueue(
        scope_setting_id=setting.id,
        reason="expired-lease",
        idempotency_key="expired-lease",
    )
    claimed = queue.claim(
        lease_token="old-lease",
        now=NOW,
        lease_for=timedelta(minutes=1),
    )
    assert claimed is not None and claimed.job_id == job_id

    expired_at = NOW + timedelta(minutes=2)
    with pytest.raises(MemoryConflictError, match="lease_conflict"):
        queue.complete(job_id=job_id, lease_token="old-lease", now=expired_at)

    reclaimed = queue.claim(
        lease_token="new-lease",
        now=expired_at,
        lease_for=timedelta(minutes=1),
    )
    assert reclaimed is not None and reclaimed.job_id == job_id
    with pytest.raises(MemoryConflictError, match="lease_conflict"):
        queue.fail(
            job_id=job_id,
            lease_token="old-lease",
            error_code="late-worker",
            retryable=False,
            now=expired_at,
        )
    queue.complete(
        job_id=job_id,
        lease_token="new-lease",
        now=expired_at + timedelta(seconds=1),
    )


def test_owner_memory_request_requires_successful_user_message(
    memory_session: Session,
) -> None:
    scope, counterpart_id = _seed_world(memory_session)
    counterpart = memory_session.get(models.WorldCharacter, counterpart_id)
    assert counterpart is not None
    thread = models.MessageThread(
        id="memory-thread",
        requester_id=scope.owner_id,
        character_id=counterpart.character_id,
        world_id=scope.world_id,
        requester_world_character_id=scope.subject_world_character_id,
        responding_world_character_id=counterpart_id,
        world_scope_status="resolved",
        selected_model="fixture-model",
        created_at=NOW,
        updated_at=NOW,
    )
    user_message = models.MessageMessage(
        thread_id=thread.id,
        role="user",
        content="이 약속은 꼭 기억해 줘.",
        status="ok",
        created_at=NOW,
    )
    assistant_message = models.MessageMessage(
        thread_id=thread.id,
        role="assistant",
        content="응, 기억할게.",
        status="ok",
        created_at=NOW + timedelta(seconds=1),
    )
    memory_session.add_all([thread, user_message, assistant_message])
    memory_session.commit()
    reader = SqlAlchemyMemorySourceEvidenceReader(memory_session)

    explicit = reader.read_evidence(
        scope=scope,
        source_type=MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
        source_id=str(user_message.id),
    )
    assert explicit is not None
    assert explicit.successful is True
    assert explicit.visible is True
    assert explicit.thread_id == thread.id

    assistant = reader.read_evidence(
        scope=scope,
        source_type=MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
        source_id=str(assistant_message.id),
    )
    assert assistant is not None
    assert assistant.successful is False


def test_sqlalchemy_source_reader_requires_observation_visibility_and_no_block(
    memory_session: Session,
) -> None:
    scope, counterpart_id = _seed_world(memory_session)
    counterpart = memory_session.get(models.WorldCharacter, counterpart_id)
    assert counterpart is not None
    post = models.Post(
        id="observed-post",
        author_character_id=counterpart.character_id,
        world_id=scope.world_id,
        author_world_character_id=counterpart_id,
        post_type="post",
        visibility="public",
        author_name="Counterpart",
        title="오늘의 훈련",
        body="함께 훈련했다.",
        search_document="오늘의 훈련 함께 훈련했다",
        created_at=NOW,
    )
    observation = models.WorldCharacterFeedObservation(
        id="observed-post-observation",
        world_id=scope.world_id,
        observer_world_character_id=scope.subject_world_character_id,
        post_id=post.id,
        status="observed",
        claim_token="claim",
        lease_expires_at=NOW + timedelta(minutes=5),
        cycle_key="cycle",
        run_id="run",
        matched_keywords=["훈련"],
        matched_fields=["title"],
        rank_score=1.0,
        post_created_at=NOW,
        claimed_at=NOW,
        observed_at=NOW,
    )
    memory_session.add_all([post, observation])
    memory_session.commit()
    reader = SqlAlchemyMemorySourceEvidenceReader(memory_session)

    evidence = reader.read_evidence(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id=post.id,
    )
    assert evidence is not None
    assert evidence.observed_by_subject is True
    assert evidence.visible is True
    assert evidence.blocked is False
    assert evidence.counterpart_world_character_id == counterpart_id
    assert evidence.observation_id == observation.id

    post.report_hidden_at = NOW
    memory_session.commit()
    hidden = reader.read_evidence(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id=post.id,
    )
    assert hidden is not None and hidden.visible is False

    post.report_hidden_at = None
    memory_session.add(
        models.WorldCharacterBlock(
            id="memory-block",
            world_id=scope.world_id,
            blocker_world_character_id=scope.subject_world_character_id,
            blocked_world_character_id=counterpart_id,
        )
    )
    memory_session.commit()
    blocked = reader.read_evidence(
        scope=scope,
        source_type=MemorySourceTypeV1.POST,
        source_id=post.id,
    )
    assert blocked is not None and blocked.blocked is True
