from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.core.db import Base
from app.core.search_text import build_post_search_document, normalize_search_text
from app.services import world_character_contracts, world_character_setup
from app.services.world_feed_search import (
    WorldFeedReadinessError,
    claim_cycle_keywords,
    claim_feed_observations,
    finalize_feed_cycle,
    load_ready_search_profile,
    search_world_feed_candidates,
    world_feed_cycle_status,
)


KEYWORDS = [
    "alchemy",
    "library",
    "runes",
    "potions",
    "academy",
    "garden",
    "research",
    "friendship",
]


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _user(suffix: str) -> models.User:
    return models.User(
        id=f"user-{suffix}",
        email=f"{suffix}@example.test",
        display_name=f"User {suffix}",
        display_name_normalized=f"user {suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _character(user: models.User, suffix: str) -> models.Character:
    return models.Character(
        id=f"character-{suffix}",
        owner_id=user.id,
        name=f"Character {suffix}",
        handle=f"character-{suffix}",
        one_liner="A curious academy resident",
        personality="Curious, observant, and warm.",
        speech_style="Calm and concise.",
        worldview="Small discoveries matter.",
        topic_preferences="Alchemy, books, and friends.",
        safety_rules="Avoid dangerous experiments.",
        persona_summary="An alchemy student at Arcana Academy.",
        moderation_status="active",
    )


def _world(owner: models.User, suffix: str = "a") -> models.World:
    return models.World(
        id=f"world-{suffix}",
        slug=f"arcana-{suffix}",
        owner_user_id=owner.id,
        name=f"Arcana {suffix}",
        tagline="A practical magic academy",
        setting_description="Students study magic together.",
        daily_life_description="Classes, meals, and clubs shape each day.",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        contract_version="world-v1",
        contract_hash=(suffix * 64)[:64],
        readiness_status="publish_ready",
        create_idempotency_key=f"create-world-{suffix}",
    )


def _action_profile() -> dict[str, dict[str, object]]:
    return {
        action: {"weight": 70, "note": f"Use {action} when it fits."}
        for action in (
            "comment",
            "reply",
            "like",
            "repost",
            "follow",
            "unfollow",
            "observe",
        )
    }


def _add_world_character(
    db: Session,
    *,
    world: models.World,
    suffix: str,
    feed_mode: str = "legacy_latest_v1",
    membership_status: str = "active",
) -> tuple[models.User, models.Character, models.WorldCharacter]:
    user = _user(suffix)
    character = _character(user, suffix)
    membership = models.WorldMembership(
        id=f"membership-{suffix}-{world.id}",
        world_id=world.id,
        user_id=user.id,
        role="member",
        status=membership_status,
        joined_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    db.add(user)
    db.flush()
    db.add(character)
    db.flush()
    db.add(membership)
    db.flush()
    character_hash = world_character_contracts.character_contract_hash(character)
    world_character = models.WorldCharacter(
        id=f"world-character-{suffix}-{world.id}",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        role_key="student",
        status="active",
        autonomous_enabled=True,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode=feed_mode,
        local_profile={"background": "alchemy student"},
        character_contract_hash=character_hash,
        world_contract_hash=world.contract_hash,
    )
    db.add(world_character)
    db.flush()
    return user, character, world_character


def _add_ready_profile(
    db: Session,
    *,
    world: models.World,
    character: models.Character,
    world_character: models.WorldCharacter,
) -> models.WorldCommunityProfile:
    profile = models.WorldCommunityProfile(
        id=f"profile-{world_character.id}",
        world_character_id=world_character.id,
        status="ready",
        visible_summary="A curious academy community participant.",
        core_interests=["alchemy", "library", "runes"],
        adjacent_interests=["garden", "friendship"],
        avoid_topics=["dangerous magic"],
        discovery_openness=70,
        search_keywords=KEYWORDS,
        action_profile=_action_profile(),
        schema_version=1,
        generator_version="fixture-v1",
        character_contract_hash=world_character_contracts.character_contract_hash(
            character
        ),
        world_contract_hash=world.contract_hash,
        provider="google",
        model="gemini-test",
        credential_id="fixture-credential",
        generated_at=datetime(2026, 8, 1, tzinfo=UTC),
        approved_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    db.add(profile)
    db.flush()
    return profile


def _post(
    db: Session,
    *,
    suffix: str,
    author: models.Character,
    world_character: models.WorldCharacter,
    title: str,
    body: str,
    topic_signature: str,
    created_at: datetime,
    deleted: bool = False,
) -> models.Post:
    post = models.Post(
        id=f"post-{suffix}",
        author_user_id=author.owner_id,
        author_character_id=author.id,
        world_id=world_character.world_id,
        author_world_character_id=world_character.id,
        author_name=author.name,
        title=title,
        body=body,
        topic_signature=topic_signature,
        search_document=build_post_search_document(
            title=title, body=body, topic_signature=topic_signature
        ),
        created_at=created_at,
        deleted_at=created_at if deleted else None,
    )
    db.add(post)
    db.flush()
    return post


def _seed_actor(db: Session):
    owner = _user("world-owner")
    db.add(owner)
    db.flush()
    world = _world(owner)
    db.add(world)
    db.flush()
    actor_user, actor, actor_wc = _add_world_character(
        db,
        world=world,
        suffix="actor",
        feed_mode="keyword_search_v1",
    )
    _add_ready_profile(
        db,
        world=world,
        character=actor,
        world_character=actor_wc,
    )
    db.add(
        models.CharacterActiveWorld(
            character_id=actor.id,
            world_character_id=actor_wc.id,
            selected_at=datetime(2026, 8, 1, tzinfo=UTC),
            idempotency_key="active-actor",
            version=1,
        )
    )
    db.flush()
    return world, actor_user, actor, actor_wc


def test_search_text_normalization_is_deterministic() -> None:
    assert normalize_search_text("  ＡLCHEMY\u200b\nClub  ", max_chars=40) == "alchemy club"
    assert build_post_search_document(
        title="Alchemy", body="  New\tPotion ", topic_signature="LAB"
    ) == (
        "alchemy\nnew potion\nlab"
    )


@pytest.mark.parametrize(
    ("keywords", "reason_code"),
    [
        (KEYWORDS[:7], "world_community_profile_invalid"),
        (["a", *KEYWORDS[1:]], "short_keyword_requires_repair"),
    ],
)
def test_profile_requires_eight_searchable_keywords(
    keywords: list[str], reason_code: str
) -> None:
    engine = _engine()
    with Session(engine) as db:
        _world_row, _actor_user, _actor, actor_wc = _seed_actor(db)
        profile = db.scalar(
            select(models.WorldCommunityProfile).where(
                models.WorldCommunityProfile.world_character_id == actor_wc.id
            )
        )
        assert profile is not None
        profile.search_keywords = keywords
        db.commit()

        with pytest.raises(WorldFeedReadinessError) as exc:
            load_ready_search_profile(db, world_character_id=actor_wc.id)

        assert exc.value.reason_code == reason_code


def test_profile_accepts_two_character_keyword_with_world_bounded_search() -> None:
    engine = _engine()
    with Session(engine) as db:
        _world_row, _actor_user, _actor, actor_wc = _seed_actor(db)
        profile = db.scalar(
            select(models.WorldCommunityProfile).where(
                models.WorldCommunityProfile.world_character_id == actor_wc.id
            )
        )
        assert profile is not None
        profile.search_keywords = ["\uc77c\uc0c1", *KEYWORDS[1:]]
        db.commit()

        ready = load_ready_search_profile(db, world_character_id=actor_wc.id)
        status = world_feed_cycle_status(db, world_character=actor_wc)
        assert status.profile_keywords_ready is True
        assert status.next_keywords == [ready.keywords[0], "library"]

        assert ready.keywords[0] == "\uc77c\uc0c1"


def test_world_scoped_search_finds_relevant_old_post_and_filters_invalid_rows() -> None:
    engine = _engine()
    now = datetime(2026, 8, 11, 7, 0, tzinfo=UTC)
    with Session(engine) as db:
        world, _actor_user, actor, actor_wc = _seed_actor(db)
        _author_user, author, author_wc = _add_world_character(
            db, world=world, suffix="author"
        )
        relevant_old = _post(
            db,
            suffix="relevant-old",
            author=author,
            world_character=author_wc,
            title="Old alchemy field notes",
            body="A careful potion experiment from last month.",
            topic_signature="alchemy research",
            created_at=now - timedelta(days=45),
        )
        for index in range(35):
            _post(
                db,
                suffix=f"recent-{index}",
                author=author,
                world_character=author_wc,
                title=f"Recent meal note {index}",
                body="A normal lunch without the selected subject.",
                topic_signature="cafeteria",
                created_at=now - timedelta(minutes=index),
            )
        _post(
            db,
            suffix="self",
            author=actor,
            world_character=actor_wc,
            title="My alchemy note",
            body="Self-authored",
            topic_signature="alchemy",
            created_at=now,
        )
        _post(
            db,
            suffix="deleted",
            author=author,
            world_character=author_wc,
            title="Deleted alchemy note",
            body="Deleted",
            topic_signature="alchemy",
            created_at=now,
            deleted=True,
        )
        other_owner = _user("other-owner")
        db.add(other_owner)
        db.flush()
        other_world = _world(other_owner, "z")
        db.add(other_world)
        db.flush()
        _other_user, other_author, other_wc = _add_world_character(
            db, world=other_world, suffix="other-world-author"
        )
        _post(
            db,
            suffix="cross-world",
            author=other_author,
            world_character=other_wc,
            title="Alchemy across Worlds",
            body="Must not cross the World boundary.",
            topic_signature="alchemy",
            created_at=now,
        )
        db.commit()

        profile = load_ready_search_profile(db, world_character_id=actor_wc.id)
        result = search_world_feed_candidates(
            db,
            profile=profile,
            keywords=("alchemy", "library"),
            allowed_policy_actions=("reply", "like", "repost", "follow"),
            now=now,
        )

        assert [candidate.post_id for candidate in result.candidates] == [
            relevant_old.id
        ]
        assert result.candidates[0].age_bucket == "older"
        assert result.candidates[0].world_local_datetime.endswith("+09:00")
        assert result.candidates[0].allowed_actions == [
            "like",
            "comment",
            "repost",
            "follow",
        ]


def test_cursor_rotates_two_keywords_and_observation_claim_is_exactly_once() -> None:
    engine = _engine()
    now = datetime(2026, 8, 11, 7, 0, tzinfo=UTC)
    with Session(engine) as db:
        world, _actor_user, _actor, actor_wc = _seed_actor(db)
        _author_user, author, author_wc = _add_world_character(
            db, world=world, suffix="author"
        )
        _post(
            db,
            suffix="alchemy",
            author=author,
            world_character=author_wc,
            title="Alchemy club",
            body="Potion research",
            topic_signature="alchemy",
            created_at=now,
        )
        db.commit()

        profile = load_ready_search_profile(db, world_character_id=actor_wc.id)
        first = claim_cycle_keywords(
            db,
            profile=profile,
            cycle_key="cycle-1",
            run_id="run-1",
        )
        assert first.keywords == ("alchemy", "library")
        search = search_world_feed_candidates(
            db,
            profile=profile,
            keywords=first.keywords,
            allowed_policy_actions=("reply", "like"),
            now=now,
        )
        claimed = claim_feed_observations(
            db,
            profile=profile,
            candidates=search.candidates,
            cycle_key="cycle-1",
            run_id="run-1",
            now=now,
        )
        assert len(claimed.observations) == 1
        second_claim = claim_feed_observations(
            db,
            profile=profile,
            candidates=search.candidates,
            cycle_key="cycle-1",
            run_id="run-2",
            now=now,
        )
        assert second_claim.observations == ()
        assert second_claim.claim_conflict_count == 1
        finalize_feed_cycle(
            db,
            profile=profile,
            claim=first,
            observations=claimed.observations,
            selected_index=None,
            selected_action=None,
            interaction_intent=None,
            comment_purpose=None,
            reason_code="model_abstained",
            public_action_execution_id=None,
            summary={"outcome": "NO_ACTION"},
            now=now,
        )
        db.commit()

        status = world_feed_cycle_status(db, world_character=actor_wc)
        assert status.profile_keyword_count == 8
        assert status.profile_keywords_ready is True
        assert status.next_keyword_offset == 2
        assert status.next_keywords == ["runes", "potions"]
        assert len(status.recent_observations) == 1
        assert status.recent_observations[0].post_title == "Alchemy club"
        assert status.recent_observations[0].author_name == author.name
        assert status.recent_observations[0].post_created_at.replace(tzinfo=UTC) == now

        duplicate = claim_cycle_keywords(
            db,
            profile=profile,
            cycle_key="cycle-1",
            run_id="run-duplicate",
        )
        assert duplicate.duplicate_cycle is True
        next_cycle = claim_cycle_keywords(
            db,
            profile=profile,
            cycle_key="cycle-2",
            run_id="run-2",
        )
        assert next_cycle.cursor_offset == 2
        assert next_cycle.keywords == ("runes", "potions")


def test_blocked_author_is_not_a_candidate() -> None:
    engine = _engine()
    now = datetime(2026, 8, 11, 7, 0, tzinfo=UTC)
    with Session(engine) as db:
        world, _actor_user, _actor, actor_wc = _seed_actor(db)
        _author_user, author, author_wc = _add_world_character(
            db, world=world, suffix="blocked"
        )
        _post(
            db,
            suffix="blocked",
            author=author,
            world_character=author_wc,
            title="Alchemy research",
            body="A relevant note.",
            topic_signature="alchemy",
            created_at=now,
        )
        db.add(
            models.WorldCharacterBlock(
                id="block-1",
                world_id=world.id,
                blocker_world_character_id=author_wc.id,
                blocked_world_character_id=actor_wc.id,
            )
        )
        db.commit()
        profile = load_ready_search_profile(db, world_character_id=actor_wc.id)
        result = search_world_feed_candidates(
            db,
            profile=profile,
            keywords=("alchemy", "library"),
            allowed_policy_actions=("reply", "like"),
            now=now,
        )
        assert result.candidates == ()


def test_character_privacy_cleanup_removes_p5_runtime_state() -> None:
    engine = _engine()
    now = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        world, actor_user, actor, actor_wc = _seed_actor(db)
        _author_user, author, author_wc = _add_world_character(
            db, world=world, suffix="cleanup-author"
        )
        post = _post(
            db,
            suffix="cleanup",
            author=author,
            world_character=author_wc,
            title="Alchemy cleanup fixture",
            body="A relevant library note.",
            topic_signature="alchemy",
            created_at=now,
        )
        profile = load_ready_search_profile(db, world_character_id=actor_wc.id)
        keyword_claim = claim_cycle_keywords(
            db,
            profile=profile,
            cycle_key="cleanup-cycle",
            run_id="cleanup-run",
        )
        candidates = search_world_feed_candidates(
            db,
            profile=profile,
            keywords=keyword_claim.keywords,
            allowed_policy_actions=("comment", "like"),
            now=now,
        )
        claimed = claim_feed_observations(
            db,
            profile=profile,
            candidates=candidates.candidates,
            cycle_key="cleanup-cycle",
            run_id="cleanup-run",
            now=now,
        )
        assert len(claimed.observations) == 1
        observation = claimed.observations[0]
        run = models.AgentRun(
            id="cleanup-run",
            user_id=actor_user.id,
            character_id=actor.id,
            agent_id="cleanup-agent",
            session_key="cleanup-session",
            status="succeeded",
        )
        db.add(run)
        db.flush()
        execution = models.AgentPublicActionExecution(
            run_id=run.id,
            character_id=actor.id,
            signature="cleanup-execution",
            scope="feed",
            action_type="comment",
            target_post_id=post.id,
            world_id=world.id,
            actor_world_character_id=actor_wc.id,
            feed_observation_id=observation.id,
            interaction_intent="ordinary_comment",
            comment_purpose="observation",
            status="succeeded",
        )
        db.add(execution)
        db.flush()
        observation.public_action_execution_id = execution.id
        db.add(
            models.WorldCharacterBlock(
                id="block-cleanup",
                world_id=world.id,
                blocker_world_character_id=actor_wc.id,
                blocked_world_character_id=author_wc.id,
            )
        )
        db.commit()

        world_character_setup.delete_setup_data_for_characters(
            db, character_ids=[actor.id]
        )
        db.commit()

        assert db.scalar(
            select(func.count(models.WorldCharacterFeedCursor.world_character_id))
        ) == 0
        assert db.scalar(
            select(func.count(models.WorldCharacterFeedObservation.id))
        ) == 0
        assert db.scalar(select(func.count(models.WorldCharacterBlock.id))) == 0
        stored_execution = db.get(models.AgentPublicActionExecution, execution.id)
        assert stored_execution is not None
        assert stored_execution.feed_observation_id is None
