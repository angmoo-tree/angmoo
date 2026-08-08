from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.core.ids import uuid7_string
from app.services import worlds as world_service
from app.services import world_foundation


def _engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        display_name_normalized=user_id,
        privacy_policy_version="test",
        terms_version="test",
    )


def _character(character_id: str, owner_id: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=character_id,
        handle=character_id,
        status="inactive",
        persona_summary="",
    )


def _world(world_id: str, owner_id: str, *, private: bool = False) -> models.World:
    return models.World(
        id=world_id,
        slug=world_id,
        owner_user_id=owner_id,
        name=world_id,
        tagline="A complete fixture World tagline",
        setting_description="s" * 200,
        daily_life_description="d" * 150,
        genre_tags=["modern"],
        tone_tags=["warm"],
        banner_alt_text="",
        timezone="Asia/Seoul",
        language="ko",
        visibility="private" if private else "public",
        join_policy="private" if private else "open",
        status="published",
        definition_version=1,
        row_version=1,
        contract_version="p0-contract-v1.1-world-creator",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        additional_generation_guidance="",
        create_idempotency_key=f"fixture-{world_id}",
    )


def _membership(
    membership_id: str,
    *,
    world_id: str,
    user_id: str,
    role: str = "member",
) -> models.WorldMembership:
    return models.WorldMembership(
        id=membership_id,
        world_id=world_id,
        user_id=user_id,
        role=role,
        status="active",
        joined_at=datetime.now(timezone.utc),
    )


def test_uuid7_string_has_expected_version_and_variant() -> None:
    value = uuid7_string(timestamp_ms=1_786_000_000_000)

    assert len(value) == 36
    assert value[14] == "7"
    assert value[19] in "89ab"


def test_world_slug_and_membership_are_unique() -> None:
    with Session(_engine()) as db:
        owner = _user("owner")
        db.add_all([owner, _world("world-a", owner.id), _world("world-b", owner.id)])
        db.flush()
        db.add_all(
            [
                _membership("membership-a", world_id="world-a", user_id=owner.id),
                _membership("membership-b", world_id="world-a", user_id=owner.id),
            ]
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_world_character_requires_membership_in_same_world_and_owner() -> None:
    with Session(_engine()) as db:
        owner = _user("owner")
        other = _user("other")
        character = _character("char-owner", owner.id)
        db.add_all([owner, other, character])
        db.flush()
        db.add_all([_world("world-a", owner.id), _world("world-b", owner.id)])
        db.flush()
        membership = _membership(
            "membership-other", world_id="world-a", user_id=other.id
        )
        db.add(membership)
        db.flush()

        with pytest.raises(world_service.WorldCharacterOwnershipError):
            world_service.validate_world_character_membership(
                db,
                world_id="world-a",
                character_id=character.id,
                membership_id=membership.id,
            )

        db.add(
            models.WorldCharacter(
                id="wc-cross-world",
                world_id="world-b",
                character_id=character.id,
                membership_id=membership.id,
                status="inactive",
                autonomous_enabled=False,
                version=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_active_mapping_must_reference_same_character() -> None:
    with Session(_engine()) as db:
        owner = _user("owner")
        char_a = _character("char-a", owner.id)
        char_b = _character("char-b", owner.id)
        db.add_all([owner, char_a, char_b])
        db.flush()
        db.add(_world("world-a", owner.id))
        db.flush()
        membership = _membership(
            "membership-owner", world_id="world-a", user_id=owner.id, role="owner"
        )
        db.add(membership)
        db.flush()
        world_character = models.WorldCharacter(
            id="wc-a",
            world_id="world-a",
            character_id=char_a.id,
            membership_id=membership.id,
            status="active",
            autonomous_enabled=False,
            version=1,
        )
        db.add(world_character)
        db.flush()
        db.add(
            models.CharacterActiveWorld(
                character_id=char_b.id,
                world_character_id=world_character.id,
                selected_at=datetime.now(timezone.utc),
                idempotency_key="switch-1",
                version=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_private_world_is_hidden_and_creator_roles_are_enforced() -> None:
    with Session(_engine()) as db:
        owner = _user("owner")
        member = _user("member")
        outsider = _user("outsider")
        world = _world("world-private", owner.id, private=True)
        db.add_all([owner, member, outsider, world])
        db.flush()
        db.add_all(
            [
                _membership(
                    "membership-owner", world_id=world.id, user_id=owner.id, role="owner"
                ),
                _membership(
                    "membership-member", world_id=world.id, user_id=member.id
                ),
            ]
        )
        db.commit()

        assert world_service.require_world_read_access(
            db, world_id=world.id, user=member
        ).id == world.id
        with pytest.raises(world_service.WorldNotFoundError):
            world_service.require_world_read_access(
                db, world_id=world.id, user=outsider
            )
        with pytest.raises(world_service.WorldCreatorRoleRequiredError):
            world_service.require_creator_access(db, world_id=world.id, user=member)
        assert world_service.require_creator_access(
            db, world_id=world.id, user=owner
        )[1].role == "owner"


def _legacy_hash(db: Session) -> str:
    values = [
        *(f"character:{item.id}:{item.owner_id}" for item in db.query(models.Character)),
        *(f"post:{item.id}:{item.title}" for item in db.query(models.Post)),
        *(
            f"daypart:{item.id}:{item.activity_daypart}:{item.summary}"
            for item in db.query(models.AgentDaypartMemoryEvent)
        ),
    ]
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def test_angmoo_global_backfill_is_idempotent_and_preserves_legacy_rows() -> None:
    with Session(_engine()) as db:
        owner = _user("owner")
        other = _user("other")
        owner.is_admin = True
        char_a = _character("char-a", owner.id)
        char_b = _character("char-b", other.id)
        db.add_all([owner, other, char_a, char_b])
        db.flush()
        post = models.Post(
            id="post-before-p1",
            author_character_id=char_a.id,
            author_name=char_a.name,
            title="legacy post",
            body="legacy body",
        )
        db.add(post)
        db.flush()
        db.add(
            models.AgentDaypartMemoryEvent(
                character_id=char_a.id,
                memory_session_key="legacy-session",
                daypart_start_date=date(2026, 8, 7),
                activity_daypart="night",
                event_type="post_created",
                source_post_id=post.id,
                summary="legacy memory",
            )
        )
        db.commit()
        before_hash = _legacy_hash(db)

        first = world_foundation.ensure_angmoo_global_foundation(db)
        db.commit()
        first_ids = {
            item.id
            for item in db.query(models.WorldCharacter).filter_by(
                world_id=world_foundation.ANGMOO_GLOBAL_WORLD_ID
            )
        }
        second = world_foundation.ensure_angmoo_global_foundation(db)
        db.commit()

        assert first.seeded is True
        assert first.owner_user_id == owner.id
        assert first.membership_count == 2
        assert first.world_character_count == 2
        assert second == first
        assert _legacy_hash(db) == before_hash
        assert db.query(models.CharacterActiveWorld).count() == 0
        assert {
            item.id
            for item in db.query(models.WorldCharacter).filter_by(
                world_id=world_foundation.ANGMOO_GLOBAL_WORLD_ID
            )
        } == first_ids
        assert {
            item.status
            for item in db.query(models.WorldCharacter).filter_by(
                world_id=world_foundation.ANGMOO_GLOBAL_WORLD_ID
            )
        } == {"inactive"}


def test_angmoo_global_backfill_waits_for_first_owner_on_empty_database() -> None:
    with Session(_engine()) as db:
        report = world_foundation.ensure_angmoo_global_foundation(db)

        assert report.seeded is False
        assert db.query(models.World).count() == 0
