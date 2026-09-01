from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.core.db import Base
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from app.domains.memory.public import (
    CANONICAL_PRIMITIVE_REGISTRY,
    CanonicalRecallOperation,
    CanonicalRecallQuery,
    CanonicalRecallService,
    CanonicalRecallStatus,
    MemoryKindV1,
    MemoryRecallDocument,
    MemoryRecallSearchQuery,
    MemoryScope,
    MemoryScopeService,
    MemorySourceTypeV1,
    MemoryValidationError,
    MemoryWriteLifecycleService,
    RecallDocumentKind,
)
from app.runtime.memory import (
    EmbeddedMemoryRecallProjection,
    MemoryRecallProjectionState,
    SqlAlchemyCanonicalRecallRepository,
    SqlAlchemyMemoryRecallDocumentSource,
    SqlAlchemyMemorySourceEvidenceReader,
    SqliteMemoryRecallIndex,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath


NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


@pytest.fixture
def runtime_factory(tmp_path: Path):
    database_path = tmp_path / "canonical.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _seed_world(session: Session) -> tuple[MemoryScope, str]:
    owner = models.User(
        id="recall-owner",
        email="recall-owner@example.test",
        display_name="Recall Owner",
        profile_setup_completed=True,
    )
    subject_character = _character("recall-subject-character", owner.id, "subject")
    counterpart_character = _character(
        "recall-counterpart-character",
        owner.id,
        "counterpart",
    )
    world = models.World(
        id="recall-world",
        slug="recall-world",
        owner_user_id=owner.id,
        name="Recall World",
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
        create_idempotency_key="recall-world",
    )
    membership = models.WorldMembership(
        id="recall-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=NOW,
    )
    subject = _world_character(
        "recall-subject",
        world.id,
        subject_character.id,
        membership.id,
    )
    counterpart = _world_character(
        "recall-counterpart",
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
        one_liner=f"{handle} one liner",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="memory",
        safety_rules="safe",
        status="inactive",
        moderation_status="active",
        execution_mode="local",
        persona_summary=f"{handle} persona",
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


def _accept_chat_memory(
    factory: sessionmaker[Session],
) -> tuple[MemoryScope, str, str, int, str]:
    with factory() as session:
        scope, counterpart_id = _seed_world(session)
        counterpart = session.get(models.WorldCharacter, counterpart_id)
        assert counterpart is not None
        thread = models.MessageThread(
            id="recall-thread",
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
        message = models.MessageMessage(
            thread_id=thread.id,
            role="user",
            content="폭우 속 합동 훈련에서 철수와 지킨 약속을 기억해 줘.",
            status="ok",
            created_at=NOW,
        )
        session.add_all([thread, message])
        session.commit()

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
        lifecycle = MemoryWriteLifecycleService(
            repository,
            SqlAlchemyMemorySourceEvidenceReader(session),
        )
        proposed = lifecycle.propose_candidate(
            scope=scope,
            source_type=MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
            source_id=str(message.id),
            memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
        )
        assert proposed.candidate is not None
        accepted = lifecycle.accept_candidate(
            scope=scope,
            candidate_id=proposed.candidate.id,
            expected_candidate_version=proposed.candidate.version,
            expected_scope_version=enabled.version,
            now=NOW,
        )
        assert accepted.item is not None
        session.commit()
        return scope, counterpart_id, thread.id, message.id, accepted.item.id


def test_private_index_is_separate_scoped_cjk_safe_and_rollbackable(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "Angmoo"
    p5_index = data_root / "search/generations/v1/angmoo-search.sqlite3"
    p5_index.parent.mkdir(parents=True)
    p5_index.write_bytes(b"p5-feed-index-sentinel")
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(data_root))
    index.open()
    scope = MemoryScope("owner-a", "world-a", "subject-a")
    first = MemoryRecallDocument(
        document_id="memory-source:item-1:evidence-1",
        memory_item_id="item-1",
        owner_id=scope.owner_id,
        world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id,
        counterpart_world_character_id="counterpart-a",
        thread_id="thread-a",
        kind=RecallDocumentKind.THREAD_MESSAGE,
        canonical_source_id="message-1",
        source_type=MemorySourceTypeV1.CHAT_MESSAGE,
        occurred_at=NOW,
        text='폭우 속 합동 훈련에서 "철수"와 지킨 약속',
        metadata={"evidence_id": "evidence-1"},
    )
    cross_scope = MemoryRecallDocument(
        document_id="memory-source:item-2:evidence-2",
        memory_item_id="item-2",
        owner_id="owner-b",
        world_id=scope.world_id,
        subject_world_character_id="subject-b",
        kind=RecallDocumentKind.THREAD_MESSAGE,
        canonical_source_id="message-2",
        source_type=MemorySourceTypeV1.CHAT_MESSAGE,
        occurred_at=NOW,
        text="폭우 속 합동 훈련에서 철수와 지킨 약속",
        metadata={"evidence_id": "evidence-2"},
    )
    doctor = index.rebuild((first, cross_scope))
    assert doctor.healthy is True
    assert Path(doctor.database_path) == (
        data_root.resolve()
        / "search/memory-recall/generations/v1/angmoo-memory-recall.sqlite3"
    )
    assert p5_index.read_bytes() == b"p5-feed-index-sentinel"

    hits = index.search(
        MemoryRecallSearchQuery(
            scope=scope,
            text='폭우 (합동)* "훈련" 약속',
            kinds=(RecallDocumentKind.THREAD_MESSAGE,),
            limit=10,
            counterpart_world_character_id="counterpart-a",
            thread_id="thread-a",
        )
    )
    assert [hit.document_id for hit in hits] == [first.document_id]

    replacement = MemoryRecallDocument(
        document_id="memory-item:item-3",
        memory_item_id="item-3",
        owner_id=scope.owner_id,
        world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id,
        kind=RecallDocumentKind.MEMORY_ITEM,
        canonical_source_id="item-3",
        occurred_at=NOW,
        text="완전히 다른 두 번째 기억",
    )
    index.rebuild((replacement,))
    assert index.search(
        MemoryRecallSearchQuery(
            scope=scope,
            text="두 번째 기억",
            kinds=(RecallDocumentKind.MEMORY_ITEM,),
            limit=10,
        )
    )
    assert index.rollback().healthy is True
    assert index.search(
        MemoryRecallSearchQuery(
            scope=scope,
            text="폭우 훈련",
            kinds=(RecallDocumentKind.THREAD_MESSAGE,),
            limit=10,
        )
    )
    assert p5_index.read_bytes() == b"p5-feed-index-sentinel"


def test_canonical_service_revalidates_stale_fts_candidates_and_memory_off(
    runtime_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    scope, counterpart_id, thread_id, message_id, item_id = _accept_chat_memory(
        runtime_factory
    )
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "data"))
    index.open()
    source = SqlAlchemyMemoryRecallDocumentSource(
        runtime_factory,
        now_factory=lambda: NOW,
    )
    index.rebuild(source.all_documents())
    service = CanonicalRecallService(
        SqlAlchemyCanonicalRecallRepository(runtime_factory),
        index,
    )

    message_result = service.execute(
        CanonicalRecallQuery(
            operation=CanonicalRecallOperation.SEARCH_THREAD_MESSAGES,
            scope=scope,
            text="폭우 합동 훈련 약속",
            counterpart_world_character_id=counterpart_id,
            thread_id=thread_id,
            limit=10,
        ),
        now=NOW,
    )
    assert message_result.status is CanonicalRecallStatus.READY
    assert len(message_result.records) == 1
    assert message_result.records[0].canonical_source_id == str(message_id)
    assert message_result.records[0].memory_item_id == item_id

    memory_result = service.execute(
        CanonicalRecallQuery(
            operation=CanonicalRecallOperation.SEARCH_MEMORY_ITEMS,
            scope=scope,
            text="철수 약속",
            limit=10,
        ),
        now=NOW,
    )
    assert [record.memory_item_id for record in memory_result.records] == [item_id]

    direct = service.execute(
        CanonicalRecallQuery(
            operation=CanonicalRecallOperation.CANONICAL_EVENT_DETAILS,
            scope=scope,
            source_references=(
                f"source:{MemorySourceTypeV1.OWNER_MEMORY_REQUEST.value}:{message_id}",
            ),
            limit=10,
        ),
        now=NOW,
    )
    assert [record.canonical_source_id for record in direct.records] == [
        str(message_id)
    ]

    with runtime_factory() as session:
        message = session.get(models.MessageMessage, message_id)
        assert message is not None
        message.content = "원문이 바뀌어 기존 projection digest가 낡았다."
        session.commit()
    stale = service.execute(
        CanonicalRecallQuery(
            operation=CanonicalRecallOperation.SEARCH_THREAD_MESSAGES,
            scope=scope,
            text="폭우 합동 훈련 약속",
            limit=10,
        ),
        now=NOW,
    )
    assert stale.status is CanonicalRecallStatus.READY
    assert stale.candidate_count == 1
    assert stale.excluded_count == 1
    assert stale.records == ()

    with runtime_factory() as session:
        repository = SqlAlchemyMemoryRepository(session)
        setting = repository.get_scope_setting(scope)
        assert setting is not None
        MemoryScopeService(repository).update(
            scope,
            expected_version=setting.version,
            enabled=False,
            retention_days=setting.retention_days,
        )
        session.commit()
    disabled = service.execute(
        CanonicalRecallQuery(
            operation=CanonicalRecallOperation.SEARCH_MEMORY_ITEMS,
            scope=scope,
            text="약속",
        ),
        now=NOW,
    )
    assert disabled.status is CanonicalRecallStatus.DISABLED
    assert disabled.records == ()
    assert disabled.reason_code == "memory_opt_out"


def test_after_commit_projection_tombstones_off_and_ignores_rollback(
    runtime_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    scope, _counterpart_id, _thread_id, _message_id, item_id = _accept_chat_memory(
        runtime_factory
    )
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "data"))
    projection = EmbeddedMemoryRecallProjection(
        index=index,
        session_factory=runtime_factory,
    )
    projection.start()
    assert projection.state is MemoryRecallProjectionState.READY
    initial_doctor = index.doctor()
    assert initial_doctor.searchable_document_count == 2

    with runtime_factory() as session:
        item = session.get(models.MemoryItem, item_id)
        assert item is not None
        item.summary = "롤백되어 색인에 들어가면 안 되는 문장"
        session.flush()
        session.rollback()
    assert not index.search(
        MemoryRecallSearchQuery(
            scope=scope,
            text="롤백되어 색인",
            kinds=(RecallDocumentKind.MEMORY_ITEM,),
            limit=10,
        )
    )

    with runtime_factory() as session:
        repository = SqlAlchemyMemoryRepository(session)
        setting = repository.get_scope_setting(scope)
        assert setting is not None
        MemoryScopeService(repository).update(
            scope,
            expected_version=setting.version,
            enabled=False,
            retention_days=setting.retention_days,
        )
        session.commit()
    assert projection.state is MemoryRecallProjectionState.READY
    doctor = index.doctor()
    assert doctor.searchable_document_count == 0
    assert doctor.tombstone_count == 2
    assert not index.search(
        MemoryRecallSearchQuery(
            scope=scope,
            text="폭우 훈련 약속",
            kinds=(RecallDocumentKind.THREAD_MESSAGE,),
            limit=10,
        )
    )

    with runtime_factory() as session:
        repository = SqlAlchemyMemoryRepository(session)
        setting = repository.get_scope_setting(scope)
        assert setting is not None
        MemoryScopeService(repository).update(
            scope,
            expected_version=setting.version,
            enabled=True,
            retention_days=setting.retention_days,
        )
        session.commit()
    assert index.doctor().searchable_document_count == 2

    with runtime_factory() as session:
        item = session.get(models.MemoryItem, item_id)
        assert item is not None
        MemoryWriteLifecycleService(
            SqlAlchemyMemoryRepository(session),
            SqlAlchemyMemorySourceEvidenceReader(session),
        ).delete_item(
            scope=scope,
            item_id=item.id,
            expected_version=item.version,
            now=NOW,
        )
        session.commit()
    deleted_doctor = index.doctor()
    assert deleted_doctor.searchable_document_count == 0
    assert deleted_doctor.tombstone_count == 2
    projection.stop()


def test_typed_registry_is_closed_and_validator_rejects_unbounded_input(
    runtime_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    scope, _counterpart_id, _thread_id, _message_id, _item_id = _accept_chat_memory(
        runtime_factory
    )
    assert set(CANONICAL_PRIMITIVE_REGISTRY) == set(CanonicalRecallOperation)
    assert len(CANONICAL_PRIMITIVE_REGISTRY) == 9
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "data"))
    index.open()
    service = CanonicalRecallService(
        SqlAlchemyCanonicalRecallRepository(runtime_factory),
        index,
    )
    with pytest.raises(MemoryValidationError, match="text_required"):
        service.execute(
            CanonicalRecallQuery(
                operation=CanonicalRecallOperation.SEARCH_MEMORY_ITEMS,
                scope=scope,
            )
        )
    with pytest.raises(MemoryValidationError, match="limit_invalid"):
        service.execute(
            CanonicalRecallQuery(
                operation=CanonicalRecallOperation.SEARCH_MEMORY_ITEMS,
                scope=scope,
                text="기억",
                limit=51,
            )
        )
