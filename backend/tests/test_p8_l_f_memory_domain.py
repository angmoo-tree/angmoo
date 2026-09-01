from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from app.domains.memory.public import (
    DEFAULT_MEMORY_RETENTION_DAYS,
    MemoryConflictError,
    MemoryKindV1,
    MemoryProviderMode,
    MemoryScope,
    MemoryScopeError,
    MemoryScopeService,
    MemoryValidationError,
    is_memory_expired,
    validate_memory_item_shape,
)


def _seed_scope(session: Session) -> MemoryScope:
    now = datetime.now(UTC)
    owner = models.User(
        id="memory-owner",
        email="memory-owner@example.test",
        display_name="Memory Owner",
        profile_setup_completed=True,
    )
    character = models.Character(
        id="memory-character",
        owner_id=owner.id,
        name="Memory Character",
        handle="memory-character",
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
        joined_at=now,
    )
    subject = models.WorldCharacter(
        id="memory-subject",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        role_key="no_specific_role",
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
        world_contract_hash="a" * 64,
        version=1,
    )
    session.add_all([owner, character, world, membership, subject])
    session.commit()
    return MemoryScope(
        owner_id=owner.id,
        world_id=world.id,
        subject_world_character_id=subject.id,
    )


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_memory_kind_v1_is_closed_and_shape_requirements_fail_closed() -> None:
    assert {kind.value for kind in MemoryKindV1} == {
        "OWNER_PREFERENCE",
        "AUTOBIOGRAPHICAL_EVENT",
        "DIRECTIONAL_RELATIONSHIP",
        "THREAD_SUMMARY",
        "ACCEPTED_JOINT_COMMITMENT",
    }
    with pytest.raises(ValueError):
        MemoryKindV1("UNBOUNDED_MODEL_KIND")
    with pytest.raises(MemoryValidationError, match="counterpart_required"):
        validate_memory_item_shape(
            kind=MemoryKindV1.DIRECTIONAL_RELATIONSHIP,
            counterpart_world_character_id=None,
            thread_id=None,
        )
    with pytest.raises(MemoryValidationError, match="thread_required"):
        validate_memory_item_shape(
            kind=MemoryKindV1.THREAD_SUMMARY,
            counterpart_world_character_id=None,
            thread_id=None,
        )


def test_retention_is_utc_deterministic_and_pin_bypasses_expiry() -> None:
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    expired_at = now - timedelta(seconds=1)
    assert is_memory_expired(
        valid_until=expired_at,
        pinned_at=None,
        now=now,
    )
    assert not is_memory_expired(
        valid_until=expired_at,
        pinned_at=now - timedelta(days=10),
        now=now,
    )
    assert not is_memory_expired(valid_until=None, pinned_at=None, now=now)


def test_scope_setting_is_created_off_and_updates_with_monotonic_version(
    memory_session: Session,
) -> None:
    scope = _seed_scope(memory_session)
    service = MemoryScopeService(SqlAlchemyMemoryRepository(memory_session))

    first = service.get_or_create(scope)
    assert first.enabled is False
    assert first.retention_days == DEFAULT_MEMORY_RETENTION_DAYS
    assert first.provider_mode is MemoryProviderMode.NONE
    assert first.version == 1

    same = service.get_or_create(scope)
    assert same.id == first.id
    assert memory_session.query(models.MemoryScopeSettingModel).count() == 1

    updated = service.update(
        scope,
        expected_version=1,
        enabled=True,
        retention_days=365,
        provider_mode=MemoryProviderMode.OPTIONAL_CONFIGURED,
    )
    assert updated.enabled is True
    assert updated.retention_days == 365
    assert updated.provider_mode is MemoryProviderMode.OPTIONAL_CONFIGURED
    assert updated.version == 2

    with pytest.raises(MemoryConflictError, match="version_conflict"):
        service.update(
            scope,
            expected_version=1,
            enabled=False,
            retention_days=180,
        )


def test_scope_control_rejects_cross_owner_or_inactive_subject(
    memory_session: Session,
) -> None:
    scope = _seed_scope(memory_session)
    repository = SqlAlchemyMemoryRepository(memory_session)

    with pytest.raises(MemoryScopeError, match="scope_invalid"):
        repository.get_or_create_scope_setting(
            MemoryScope(
                owner_id="another-owner",
                world_id=scope.world_id,
                subject_world_character_id=scope.subject_world_character_id,
            )
        )

    subject = memory_session.get(models.WorldCharacter, scope.subject_world_character_id)
    assert subject is not None
    subject.status = "left"
    memory_session.commit()
    with pytest.raises(MemoryScopeError, match="scope_invalid"):
        repository.get_or_create_scope_setting(scope)


def test_database_rejects_unknown_provider_mode(memory_session: Session) -> None:
    scope = _seed_scope(memory_session)
    memory_session.add(
        models.MemoryScopeSettingModel(
            id="bad-provider",
            owner_id=scope.owner_id,
            world_id=scope.world_id,
            subject_world_character_id=scope.subject_world_character_id,
            enabled=False,
            retention_days=180,
            provider_mode="model-controls-scope",
            version=1,
        )
    )
    with pytest.raises(IntegrityError):
        memory_session.commit()


def test_database_rejects_pending_maintenance_job_with_lease(
    memory_session: Session,
) -> None:
    scope = _seed_scope(memory_session)
    setting = MemoryScopeService(
        SqlAlchemyMemoryRepository(memory_session)
    ).get_or_create(scope)
    memory_session.add(
        models.MemoryMaintenanceJob(
            id="pending-with-lease",
            scope_setting_id=setting.id,
            reason="fixture",
            idempotency_key="pending-with-lease",
            lease_token="lease-token",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    with pytest.raises(IntegrityError):
        memory_session.commit()
    memory_session.rollback()
