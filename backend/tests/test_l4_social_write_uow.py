from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.core.db import Base
from app.domains.social.application import (
    apply_validated_autonomous_result,
    create_owner_post,
    create_owner_reply,
)
from app.domains.social.contracts import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialWriteNotFoundError,
    SocialWriteRetryableError,
    ValidatedAutonomousWriteCommand,
)
from app.runtime.social.sqlalchemy_unit_of_work import (
    SqlAlchemySocialWriteUnitOfWork,
)
from app.core.sqlite_concurrency import SqliteRetryPolicy
from app.services import world_character_contracts


def _session_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'social-write.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    _seed(factory)
    return factory


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        display_name_normalized=user_id,
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _character(character_id: str, owner_id: str, name: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=name,
        handle=f"{character_id}-handle",
        one_liner="fixture",
        personality="warm",
        speech_style="brief",
        worldview="friends matter",
        topic_preferences="school",
        safety_rules="safe",
        persona_summary="fixture",
        moderation_status="active",
    )


def _seed(factory: sessionmaker[Session]) -> None:
    now = datetime.now(UTC)
    owner = _user("social-uow-owner")
    owner_character = _character("social-uow-owner-character", owner.id, "Owner Bird")
    autonomous_character = _character(
        "social-uow-autonomous-character", owner.id, "Mango"
    )
    world = models.World(
        id="social-uow-world",
        slug="social-uow-world",
        owner_user_id=owner.id,
        name="Social UoW World",
        tagline="fixture",
        setting_description="fixture",
        daily_life_description="fixture",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
        banner_alt_text="",
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        definition_version=1,
        row_version=1,
        contract_version="world-v1",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        additional_generation_guidance="",
        create_idempotency_key="social-uow-world-create",
    )
    membership = models.WorldMembership(
        id="social-uow-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=now,
    )
    role = models.WorldRole(
        id="social-uow-role",
        world_id=world.id,
        role_key="resident",
        name="Resident",
        description="fixture",
        responsibilities=[],
        allowed_activity_scope=[],
        autonomous_allowed=True,
        status="enabled",
    )
    owner_actor = models.WorldCharacter(
        id="social-uow-owner-actor",
        world_id=world.id,
        character_id=owner_character.id,
        membership_id=membership.id,
        role_key="resident",
        status="active",
        control_mode="owner_controlled",
        owner_user_id=owner.id,
        autonomous_enabled=False,
        activity_runtime_mode="legacy_resident_v1",
        feed_runtime_mode="legacy_latest_v1",
        local_profile={"display_name": owner_character.name},
        character_contract_hash=world_character_contracts.character_contract_hash(
            owner_character
        ),
        world_contract_hash=world.contract_hash,
    )
    autonomous_actor = models.WorldCharacter(
        id="social-uow-autonomous-actor",
        world_id=world.id,
        character_id=autonomous_character.id,
        membership_id=membership.id,
        role_key="resident",
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode="keyword_search_v1",
        local_profile={"display_name": autonomous_character.name},
        character_contract_hash=world_character_contracts.character_contract_hash(
            autonomous_character
        ),
        world_contract_hash=world.contract_hash,
    )
    with factory() as db:
        db.add_all([owner, owner_character, autonomous_character, world])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="social-uow-installation",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="fixture",
                claimed_at=now,
            )
        )
        db.add_all([membership, role])
        db.flush()
        db.add_all([owner_actor, autonomous_actor])
        db.flush()
        db.add_all(
            [
                models.CharacterActiveWorld(
                    character_id=owner_character.id,
                    world_character_id=owner_actor.id,
                    selected_at=now,
                    idempotency_key="social-uow-owner-active",
                    version=1,
                ),
                models.CharacterActiveWorld(
                    character_id=autonomous_character.id,
                    world_character_id=autonomous_actor.id,
                    selected_at=now,
                    idempotency_key="social-uow-autonomous-active",
                    version=1,
                ),
            ]
        )
        db.add(
            models.Post(
                id="social-uow-target-post",
                author_user_id=owner.id,
                author_character_id=autonomous_character.id,
                world_id=world.id,
                author_world_character_id=autonomous_actor.id,
                post_type="post",
                visibility="public",
                author_name=autonomous_character.name,
                title="Target post",
                body="An autonomous source post.",
                search_document="target autonomous",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()


def _owner_post() -> OwnerPostCommand:
    return OwnerPostCommand(
        world_id="social-uow-world",
        current_user_id="social-uow-owner",
        idempotency_key="owner-concurrent-post",
        title="Owner source",
        body="Owner writes while Mango writes.",
    )


def _autonomous_post() -> ValidatedAutonomousWriteCommand:
    return ValidatedAutonomousWriteCommand(
        world_id="social-uow-world",
        actor_world_character_id="social-uow-autonomous-actor",
        idempotency_key="autonomous-concurrent-post",
        operation="post",
        title="Mango source",
        body="A deterministic validated result.",
    )


def test_owner_and_autonomous_writers_serialize_and_commit_once(tmp_path) -> None:
    factory = _session_factory(tmp_path)
    barrier = Barrier(2)
    policy = SqliteRetryPolicy(maximum_elapsed_seconds=2.0)

    def owner_write():
        with factory() as db:
            barrier.wait()
            return create_owner_post(
                SqlAlchemySocialWriteUnitOfWork(db, retry_policy=policy),
                _owner_post(),
            )

    def autonomous_write():
        with factory() as db:
            barrier.wait()
            return apply_validated_autonomous_result(
                SqlAlchemySocialWriteUnitOfWork(db, retry_policy=policy),
                _autonomous_post(),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(owner_write), executor.submit(autonomous_write)]
        results = [future.result(timeout=5) for future in futures]
    assert all(not result.replayed for result in results)

    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 3
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 2
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 2
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 2
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0

    with factory() as db:
        assert create_owner_post(
            SqlAlchemySocialWriteUnitOfWork(db), _owner_post()
        ).replayed
    with factory() as db:
        assert apply_validated_autonomous_result(
            SqlAlchemySocialWriteUnitOfWork(db), _autonomous_post()
        ).replayed
    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 3
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 2


def test_forced_writer_lock_returns_typed_retry_and_same_request_recovers(
    tmp_path,
) -> None:
    factory = _session_factory(tmp_path)
    lock_session = factory()
    lock_session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    policy = SqliteRetryPolicy(
        max_attempts=2,
        initial_delay_seconds=0.005,
        maximum_delay_seconds=0.005,
        maximum_elapsed_seconds=0.02,
    )
    try:
        with factory() as db:
            with pytest.raises(SocialWriteRetryableError) as raised:
                create_owner_post(
                    SqlAlchemySocialWriteUnitOfWork(db, retry_policy=policy),
                    _owner_post(),
                )
            assert raised.value.reason_code == "sqlite_busy_retry_exhausted"
    finally:
        lock_session.rollback()
        lock_session.close()

    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 1
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 0
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 0

    with factory() as db:
        result = create_owner_post(SqlAlchemySocialWriteUnitOfWork(db), _owner_post())
        assert result.replayed is False
    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 2
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 1
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 1


def test_cross_world_reply_target_fails_closed_without_partial_rows(tmp_path) -> None:
    factory = _session_factory(tmp_path)
    now = datetime.now(UTC)
    with factory() as db:
        db.add(
            models.World(
                id="social-uow-other-world",
                slug="social-uow-other-world",
                owner_user_id="social-uow-owner",
                name="Other World",
                tagline="fixture",
                setting_description="fixture",
                daily_life_description="fixture",
                genre_tags=["fantasy"],
                tone_tags=["cold"],
                banner_alt_text="",
                timezone="Asia/Seoul",
                language="ko",
                visibility="public",
                join_policy="open",
                status="published",
                definition_version=1,
                row_version=1,
                contract_version="world-v1",
                contract_hash="b" * 64,
                readiness_status="publish_ready",
                additional_generation_guidance="",
                create_idempotency_key="social-uow-other-world-create",
            )
        )
        db.flush()
        other_character = db.get(models.Character, "social-uow-autonomous-character")
        assert other_character is not None
        db.add_all(
            [
                models.WorldMembership(
                    id="social-uow-other-membership",
                    world_id="social-uow-other-world",
                    user_id="social-uow-owner",
                    role="owner",
                    status="active",
                    joined_at=now,
                ),
                models.WorldRole(
                    id="social-uow-other-role",
                    world_id="social-uow-other-world",
                    role_key="resident",
                    name="Resident",
                    description="fixture",
                    responsibilities=[],
                    allowed_activity_scope=[],
                    autonomous_allowed=True,
                    status="enabled",
                ),
            ]
        )
        db.flush()
        db.add(
            models.WorldCharacter(
                id="social-uow-other-actor",
                world_id="social-uow-other-world",
                character_id=other_character.id,
                membership_id="social-uow-other-membership",
                role_key="resident",
                status="active",
                control_mode="autonomous",
                owner_user_id=None,
                autonomous_enabled=True,
                activity_runtime_mode="routine_resident_v1",
                feed_runtime_mode="keyword_search_v1",
                local_profile={"display_name": other_character.name},
                character_contract_hash=world_character_contracts.character_contract_hash(
                    other_character
                ),
                world_contract_hash="b" * 64,
            )
        )
        db.flush()
        db.add(
            models.Post(
                id="social-uow-cross-world-post",
                author_user_id="social-uow-owner",
                author_character_id="social-uow-autonomous-character",
                world_id="social-uow-other-world",
                author_world_character_id="social-uow-other-actor",
                post_type="post",
                visibility="public",
                author_name="Mango",
                title="Other World target",
                body="This target must not cross into the selected World.",
                search_document="other world target",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    command = OwnerReplyCommand(
        world_id="social-uow-world",
        current_user_id="social-uow-owner",
        idempotency_key="owner-cross-world-reply",
        target_post_id="social-uow-cross-world-post",
        body="This reply must fail closed.",
    )
    with (
        factory() as db,
        pytest.raises(SocialWriteNotFoundError, match="reply_target_unavailable"),
    ):
        create_owner_reply(SqlAlchemySocialWriteUnitOfWork(db), command)

    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 2
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 0
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 0
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 0


@pytest.mark.parametrize(
    "failure_stage",
    [
        "after_source_post",
        "after_source_event",
        "after_source_evidence",
        "before_commit",
    ],
)
def test_owner_post_failure_injection_rolls_back_every_canonical_row(
    tmp_path, failure_stage: str
) -> None:
    factory = _session_factory(tmp_path)

    def fail(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"injected:{stage}")

    with (
        factory() as db,
        pytest.raises(RuntimeError, match=f"injected:{failure_stage}"),
    ):
        create_owner_post(
            SqlAlchemySocialWriteUnitOfWork(db, failure_injector=fail),
            _owner_post(),
        )

    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 1
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 0
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 0


def test_owner_reply_event_evidence_inbox_are_atomic_without_relationship_delta(
    tmp_path,
) -> None:
    factory = _session_factory(tmp_path)
    command = OwnerReplyCommand(
        world_id="social-uow-world",
        current_user_id="social-uow-owner",
        idempotency_key="owner-atomic-reply",
        target_post_id="social-uow-target-post",
        body="I will answer in this World.",
    )
    with factory() as db:
        result = create_owner_reply(SqlAlchemySocialWriteUnitOfWork(db), command)
        assert result.delivery.inbox_status == "pending"
        assert result.delivery.inbox_candidate_id is not None
    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 2
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 1
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 1
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0


def test_reply_failure_after_inbox_candidate_rolls_back_source_and_delivery(
    tmp_path,
) -> None:
    factory = _session_factory(tmp_path)

    def fail(stage: str) -> None:
        if stage == "after_inbox_candidate":
            raise RuntimeError("injected:after_inbox_candidate")

    command = OwnerReplyCommand(
        world_id="social-uow-world",
        current_user_id="social-uow-owner",
        idempotency_key="owner-failing-reply",
        target_post_id="social-uow-target-post",
        body="This transaction must disappear.",
    )
    with (
        factory() as db,
        pytest.raises(RuntimeError, match="injected:after_inbox_candidate"),
    ):
        create_owner_reply(
            SqlAlchemySocialWriteUnitOfWork(db, failure_injector=fail), command
        )
    with factory() as db:
        assert db.scalar(select(func.count(models.Post.id))) == 1
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 0
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 0
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 0
