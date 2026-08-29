from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base, create_database_engine, create_session_factory
from app.domains.world_characters.api.setup_schemas import WorldCharacterEntryCreate
from app.domains.world_characters.infrastructure.autonomous_setup_contracts import (
    character_contract_hash,
)
from app.domains.world_characters.infrastructure.sqlalchemy_autonomous_setup import (
    enter_world,
)
from app.domains.world_characters.infrastructure.sqlalchemy_runtime_modes import (
    reconcile_local_autonomous_runtime_modes,
)


DAYPARTS = ("dawn", "morning", "afternoon", "evening")


def _user() -> models.User:
    return models.User(
        id="owner",
        email="owner@example.test",
        display_name="owner",
        display_name_normalized="owner",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _world(world_id: str) -> models.World:
    return models.World(
        id=world_id,
        slug=world_id,
        owner_user_id="owner",
        name=world_id,
        tagline="fixture",
        setting_description="fixture",
        daily_life_description="fixture",
        genre_tags=["hero-school"],
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
        contract_hash=(world_id * 64)[:64],
        readiness_status="publish_ready",
        additional_generation_guidance="",
        create_idempotency_key=f"create-{world_id}",
    )


def _character(character_id: str, *, execution_mode: str = "llm") -> models.Character:
    return models.Character(
        id=character_id,
        owner_id="owner",
        name=character_id,
        handle=character_id,
        one_liner="fixture",
        personality="fixture",
        speech_style="fixture",
        worldview="fixture",
        topic_preferences="fixture",
        safety_rules="fixture",
        persona_summary="fixture",
        execution_mode=execution_mode,
        moderation_status="active",
    )


def _seed_world_scope(db: Session, world_id: str) -> None:
    db.add(_world(world_id))
    db.flush()
    db.add_all(
        [
            models.WorldMembership(
                id=f"membership-{world_id}",
                world_id=world_id,
                user_id="owner",
                role="owner",
                status="active",
                joined_at=datetime.now(UTC),
            ),
            models.WorldRole(
                id=f"role-{world_id}",
                world_id=world_id,
                role_key="student",
                name="학생",
                description="fixture",
                responsibilities=[],
                allowed_activity_scope=[],
                autonomous_allowed=True,
                status="enabled",
            ),
        ]
    )


def _seed_ready_entry(
    db: Session,
    *,
    world_id: str,
    suffix: str,
    entry_marker: bool = True,
    status: str = "active",
    feed_runtime_mode: str = "legacy_latest_v1",
) -> models.WorldCharacter:
    character = _character(f"character-{suffix}")
    db.add(character)
    db.flush()
    world = db.get(models.World, world_id)
    assert world is not None
    character_hash = character_contract_hash(character)
    world_character = models.WorldCharacter(
        id=f"world-character-{suffix}",
        world_id=world_id,
        character_id=character.id,
        membership_id=f"membership-{world_id}",
        role_key="student",
        status=status,
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=status == "active",
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode=feed_runtime_mode,
        local_profile=(
            {"entry_idempotency_key": f"entry-{suffix}"}
            if entry_marker
            else {"background": "explicit legacy fixture"}
        ),
        character_contract_hash=character_hash,
        world_contract_hash=world.contract_hash,
        version=7,
    )
    db.add(world_character)
    db.flush()
    profile = models.WorldCommunityProfile(
        id=f"profile-{suffix}",
        world_character_id=world_character.id,
        status="ready",
        visible_summary="fixture",
        core_interests=["훈련", "친구", "학교"],
        adjacent_interests=["도시", "교실"],
        avoid_topics=[],
        discovery_openness=50,
        search_keywords=[f"키워드-{index}" for index in range(8)],
        action_profile={},
        schema_version=1,
        generator_version="fixture",
        character_contract_hash=character_hash,
        world_contract_hash=world.contract_hash,
        provider="fixture",
        model="fixture",
        credential_id=f"credential-{suffix}",
        generated_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    repertoire = models.WorldActivityRepertoire(
        id=f"repertoire-{suffix}",
        world_character_id=world_character.id,
        status="ready",
        schema_version=1,
        generator_version="fixture",
        character_contract_hash=character_hash,
        world_contract_hash=world.contract_hash,
        community_profile_id=profile.id,
        provider="fixture",
        model="fixture",
        credential_id=f"credential-{suffix}",
        validation_summary={"candidate_count": 40},
        generated_at=datetime.now(UTC),
        approved_at=datetime.now(UTC),
    )
    db.add(profile)
    db.flush()
    db.add(repertoire)
    db.flush()
    for daypart in DAYPARTS:
        for ordinal in range(1, 11):
            db.add(
                models.WorldActivityCandidate(
                    id=f"candidate-{suffix}-{daypart}-{ordinal}",
                    repertoire_id=repertoire.id,
                    daypart=daypart,
                    ordinal=ordinal,
                    activity_kind="duty",
                    title=f"{daypart}-{ordinal}",
                    activity_seed=f"fixture activity {daypart} {ordinal}",
                    place_key=None,
                    social_mode="open_to_interaction",
                    canonical_signature=(
                        f"{suffix}-{daypart}-{ordinal:02d}".ljust(64, "0")[:64]
                    ),
                    enabled=True,
                )
            )
    return world_character


def _seed_excluded_entry(
    db: Session,
    *,
    world_id: str,
    suffix: str,
    status: str,
    control_mode: str = "autonomous",
) -> models.WorldCharacter:
    character = _character(f"character-{suffix}")
    db.add(character)
    db.flush()
    world = db.get(models.World, world_id)
    assert world is not None
    world_character = models.WorldCharacter(
        id=f"world-character-{suffix}",
        world_id=world_id,
        character_id=character.id,
        membership_id=f"membership-{world_id}",
        role_key="student",
        status=status,
        control_mode=control_mode,
        owner_user_id="owner" if control_mode == "owner_controlled" else None,
        autonomous_enabled=False,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode="legacy_latest_v1",
        local_profile={"entry_idempotency_key": f"entry-{suffix}"},
        character_contract_hash=character_contract_hash(character),
        world_contract_hash=world.contract_hash,
        version=4,
    )
    db.add(world_character)
    db.flush()
    return world_character


def _seed_pending_inbox(db: Session, target: models.WorldCharacter) -> None:
    actor_character = _character("character-owner-controlled", execution_mode="local")
    db.add(actor_character)
    db.flush()
    actor = models.WorldCharacter(
        id="world-character-owner-controlled",
        world_id=target.world_id,
        character_id=actor_character.id,
        membership_id=target.membership_id,
        role_key="student",
        status="active",
        control_mode="owner_controlled",
        owner_user_id="owner",
        autonomous_enabled=False,
        activity_runtime_mode="legacy_resident_v1",
        feed_runtime_mode="legacy_latest_v1",
        version=3,
    )
    db.add(actor)
    db.flush()
    root = models.Post(
        id="post-root",
        author_character_id=target.character_id,
        world_id=target.world_id,
        author_world_character_id=target.id,
        post_type="post",
        visibility="public",
        author_name="target",
        title="훈련 기록",
        body="오늘의 훈련을 마쳤다.",
        search_document="훈련 기록",
    )
    reply = models.Post(
        id="post-reply",
        author_user_id="owner",
        author_character_id=actor.character_id,
        world_id=target.world_id,
        author_world_character_id=actor.id,
        reply_to_post_id=root.id,
        post_type="reply",
        visibility="public",
        author_name="owner",
        title="Re: 훈련 기록",
        body="좋은 말씀이네요.",
        search_document="좋은 말씀이네요",
    )
    db.add_all([root, reply])
    db.flush()
    db.add(
        models.OwnerManualInboxCandidate(
            id="pending-inbox",
            world_id=target.world_id,
            actor_world_character_id=actor.id,
            target_world_character_id=target.id,
            source_reply_post_id=reply.id,
            target_post_id=root.id,
            status="pending",
            version=1,
        )
    )


def _seed_existing_social_evidence(
    db: Session,
    *,
    actor: models.WorldCharacter,
    target: models.WorldCharacter,
) -> None:
    event = models.SocialEvent(
        id="existing-social-event",
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        target_world_character_id=target.id,
        event_type="comment_created",
        result="succeeded",
        occurred_at=datetime.now(UTC),
        idempotency_key="existing-social-event-key",
        schema_version="social-event-v1",
        retrieval_status="eligible",
    )
    db.add(event)
    db.flush()
    relationship = models.RelationshipState(
        id="existing-relationship-state",
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        target_world_character_id=target.id,
        familiarity=1,
        affinity=0,
        trust=0,
        tension=0,
        interaction_count=1,
        last_event_id=event.id,
        last_event_at=event.occurred_at,
        version=1,
    )
    db.add(relationship)
    db.flush()
    db.add_all(
        [
            models.RelationshipStateChange(
                id="existing-relationship-change",
                relationship_state_id=relationship.id,
                social_event_id=event.id,
                world_id=actor.world_id,
                actor_world_character_id=actor.id,
                target_world_character_id=target.id,
                valence="neutral",
                intensity="low",
                delta_familiarity=1,
                delta_affinity=0,
                delta_trust=0,
                delta_tension=0,
                before_snapshot={"familiarity": 0},
                after_snapshot={"familiarity": 1},
                applied=True,
                not_applied_reason=None,
            ),
            models.GraphProjectionOutbox(
                id="existing-graph-outbox",
                world_id=actor.world_id,
                source_event_id=event.id,
                projection_type="social_event",
                payload_version="relationship-v1",
                payload={
                    "world_id": actor.world_id,
                    "source_event_id": event.id,
                    "actor_world_character_id": actor.id,
                    "target_world_character_id": target.id,
                },
                source_signature="e" * 64,
                dedupe_key="existing-graph-outbox-dedupe",
                status="succeeded",
                attempt_count=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ]
    )


def test_file_backed_repair_is_bounded_idempotent_and_preserves_evidence(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "runtime-mode-repair.sqlite3"
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as db:
        db.add(_user())
        db.flush()
        _seed_world_scope(db, "world-local")
        _seed_world_scope(db, "world-imported")
        eligible = _seed_ready_entry(
            db,
            world_id="world-local",
            suffix="eligible",
        )
        eligible_second = _seed_ready_entry(
            db,
            world_id="world-local",
            suffix="eligible-second",
        )
        source_missing = _seed_ready_entry(
            db,
            world_id="world-local",
            suffix="explicit-legacy",
            entry_marker=False,
        )
        imported = _seed_ready_entry(
            db,
            world_id="world-imported",
            suffix="imported",
        )
        already_ready = _seed_ready_entry(
            db,
            world_id="world-local",
            suffix="already-ready",
            feed_runtime_mode="keyword_search_v1",
        )
        stale = _seed_ready_entry(
            db,
            world_id="world-local",
            suffix="stale-contract",
        )
        stale.character_contract_hash = "f" * 64
        excluded = {
            status: _seed_excluded_entry(
                db,
                world_id="world-local",
                suffix=f"excluded-{status}",
                status=status,
            )
            for status in ("left", "rejected", "banned")
        }
        excluded["owner_controlled"] = _seed_excluded_entry(
            db,
            world_id="world-local",
            suffix="excluded-owner-controlled",
            status="inactive",
            control_mode="owner_controlled",
        )
        excluded["partial_rollback"] = _seed_excluded_entry(
            db,
            world_id="world-local",
            suffix="excluded-partial-rollback",
            status="active",
        )
        _seed_pending_inbox(db, eligible)
        _seed_existing_social_evidence(
            db,
            actor=eligible,
            target=eligible_second,
        )
        db.add(
            models.WorldPackageImport(
                import_id="import-fixture",
                local_owner_id="owner",
                package_id="package-fixture",
                package_version=1,
                content_digest="d" * 64,
                imported_world_id="world-imported",
                import_mode="new_world",
                trust_state="locally_exported",
                license_expression="MIT",
                idempotency_key="import-fixture",
                imported_at=datetime.now(UTC),
            )
        )
        db.commit()
        ids = {
            "eligible": eligible.id,
            "eligible_second": eligible_second.id,
            "source_missing": source_missing.id,
            "imported": imported.id,
            "already_ready": already_ready.id,
            "stale": stale.id,
            **{f"excluded_{key}": value.id for key, value in excluded.items()},
        }

    with session_factory() as db:
        owner = db.get(models.User, "owner")
        assert owner is not None
        replay = enter_world(
            db,
            world_id="world-local",
            user=owner,
            data=WorldCharacterEntryCreate(
                character_id="character-eligible",
                role_key="student",
                local_background="",
                idempotency_key="entry-eligible",
            ),
        )
        assert replay.id == ids["eligible"]
        assert replay.reused is True
        replayed_row = db.get(models.WorldCharacter, replay.id)
        assert replayed_row is not None
        assert replayed_row.feed_runtime_mode == "keyword_search_v1"
        assert replayed_row.version == 8

    first = reconcile_local_autonomous_runtime_modes(session_factory)
    second = reconcile_local_autonomous_runtime_modes(session_factory)

    assert first.scanned_count == 5
    assert first.repaired_count == 1
    assert dict(first.skipped_reasons) == {
        "imported_world": 1,
        "profile_not_ready": 1,
        "source_marker_missing": 1,
        "world_character_contract_stale": 1,
    }
    assert second.scanned_count == 4
    assert second.repaired_count == 0
    with session_factory() as db:
        repaired = db.get(models.WorldCharacter, ids["eligible"])
        repaired_second = db.get(models.WorldCharacter, ids["eligible_second"])
        explicit_legacy = db.get(models.WorldCharacter, ids["source_missing"])
        imported = db.get(models.WorldCharacter, ids["imported"])
        already_ready = db.get(models.WorldCharacter, ids["already_ready"])
        assert repaired is not None
        assert repaired.activity_runtime_mode == "routine_resident_v1"
        assert repaired.feed_runtime_mode == "keyword_search_v1"
        assert repaired.version == 8
        assert repaired_second is not None
        assert repaired_second.activity_runtime_mode == "routine_resident_v1"
        assert repaired_second.feed_runtime_mode == "keyword_search_v1"
        assert repaired_second.version == 8
        assert explicit_legacy is not None
        assert explicit_legacy.feed_runtime_mode == "legacy_latest_v1"
        assert imported is not None
        assert imported.feed_runtime_mode == "legacy_latest_v1"
        assert already_ready is not None
        assert already_ready.feed_runtime_mode == "keyword_search_v1"
        stale = db.get(models.WorldCharacter, ids["stale"])
        assert stale is not None
        assert stale.feed_runtime_mode == "legacy_latest_v1"
        for key in (
            "left",
            "rejected",
            "banned",
            "owner_controlled",
            "partial_rollback",
        ):
            excluded_row = db.get(
                models.WorldCharacter,
                ids[f"excluded_{key}"],
            )
            assert excluded_row is not None
            assert excluded_row.feed_runtime_mode == "legacy_latest_v1"
        pending = db.get(models.OwnerManualInboxCandidate, "pending-inbox")
        assert pending is not None
        assert pending.status == "pending"
        assert pending.consumed_at is None
        assert db.scalar(select(func.count()).select_from(models.Post)) == 2
        assert db.scalar(select(func.count()).select_from(models.AgentRun)) == 0
        assert db.scalar(select(func.count()).select_from(models.SocialEvent)) == 1
        assert db.scalar(select(func.count()).select_from(models.RelationshipState)) == 1
        assert (
            db.scalar(select(func.count()).select_from(models.RelationshipStateChange))
            == 1
        )
        assert (
            db.scalar(select(func.count()).select_from(models.GraphProjectionOutbox))
            == 1
        )
    engine.dispose()
