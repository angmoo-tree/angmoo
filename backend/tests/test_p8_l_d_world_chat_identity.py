from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app import models
from app.domains.chat.api import schemas
from app.runtime.chat import sqlalchemy_service as world_chat


def _create_tables(engine) -> None:
    for table in (
        models.User.__table__,
        models.InstallationIdentity.__table__,
        models.Character.__table__,
        models.World.__table__,
        models.WorldMembership.__table__,
        models.WorldCharacter.__table__,
        models.WorldCharacterBlock.__table__,
        models.UserMessagePreference.__table__,
        models.MessageThread.__table__,
        models.MessageMessage.__table__,
    ):
        table.create(engine)


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        profile_setup_completed=True,
    )


def _installation(owner_id: str) -> models.InstallationIdentity:
    return models.InstallationIdentity(
        singleton_key="local-installation",
        installation_id="p8-l-d-fixture",
        owner_user_id=owner_id,
        bootstrap_state="claimed",
        local_label="P8-L-D fixture",
        claimed_at=datetime.now(UTC),
    )


def _character(character_id: str, owner_id: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=character_id,
        handle=character_id,
        one_liner="",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="chat",
        safety_rules="safe",
        status="inactive",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


def _world(world_id: str, owner_id: str) -> models.World:
    return models.World(
        id=world_id,
        slug=world_id,
        owner_user_id=owner_id,
        name=world_id,
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
        create_idempotency_key=world_id,
    )


def _membership(
    world_id: str,
    user_id: str,
    *,
    membership_id: str | None = None,
    role: str = "owner",
    status: str = "active",
) -> models.WorldMembership:
    return models.WorldMembership(
        id=membership_id or f"membership-{world_id}",
        world_id=world_id,
        user_id=user_id,
        role=role,
        status=status,
        joined_at=datetime.now(UTC),
    )


def _world_character(
    world_id: str,
    character_id: str,
    *,
    owner_id: str | None = None,
    membership_id: str | None = None,
    suffix: str,
) -> models.WorldCharacter:
    owner_controlled = owner_id is not None
    return models.WorldCharacter(
        id=f"wc-{suffix}",
        world_id=world_id,
        character_id=character_id,
        membership_id=membership_id or f"membership-{world_id}",
        role_key="no_specific_role",
        status="active",
        control_mode="owner_controlled" if owner_controlled else "autonomous",
        owner_user_id=owner_id,
        autonomous_enabled=not owner_controlled,
        world_contract_hash="a" * 64,
        version=1,
    )


def _seed_world(
    db: Session,
    *,
    owner: models.User,
    responder_owner: models.User,
    world_id: str,
    requester_character: models.Character,
    responding_character: models.Character,
    suffix: str,
) -> tuple[models.WorldCharacter, models.WorldCharacter]:
    requester = _world_character(
        world_id,
        requester_character.id,
        owner_id=owner.id,
        suffix=f"requester-{suffix}",
    )
    responding = _world_character(
        world_id, responding_character.id,
        membership_id=f"membership-{world_id}-responder",
        suffix=f"responding-{suffix}",
    )
    db.add_all(
        [
            _world(world_id, owner.id),
            _membership(world_id, owner.id),
            _membership(
                world_id,
                responder_owner.id,
                membership_id=f"membership-{world_id}-responder",
                role="member",
            ),
            requester,
            responding,
        ]
    )
    db.flush()
    return requester, responding


def test_world_chat_create_or_get_binds_roles_and_reuses_active_tuple() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        requester, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()

        first = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        second = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )

        assert first.outcome == "created"
        assert second.outcome == "reused"
        assert first.thread is not None and second.thread is not None
        assert first.thread.id == second.thread.id
        assert first.thread.world_id == "world-a"
        assert first.thread.requester.world_character_id == requester.id
        assert first.thread.responding.world_character_id == responding.id
        assert db.scalar(select(func.count(models.MessageThread.id))) == 1


def test_world_chat_requester_zero_and_spoof_fail_closed() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        responder_character = _character("responding-character", responder_owner.id)
        db.add_all([owner, responder_owner, _installation(owner.id), responder_character])
        db.flush()
        db.add_all([_world("world-a", owner.id), _membership("world-a", owner.id)])
        responder = _world_character(
            "world-a", responder_character.id, suffix="responding-a"
        )
        db.add(responder)
        db.commit()

        missing = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responder.id
            ),
        )
        assert missing.outcome == "resolution_required"
        assert missing.resolution_code == "requester_missing"
        assert db.scalar(select(func.count(models.MessageThread.id))) == 0


def test_world_chat_cross_world_self_and_block_are_rejected() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        requester, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        _, responding_b = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-b",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="b",
        )
        db.commit()

        with pytest.raises(world_chat.MessageNotFoundError):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding_b.id
                ),
            )
        with pytest.raises(world_chat.MessageValidationError):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=requester.id
                ),
            )
        db.add(
            models.WorldCharacterBlock(
                id="block-a",
                world_id="world-a",
                blocker_world_character_id=responding.id,
                blocked_world_character_id=requester.id,
            )
        )
        db.commit()
        with pytest.raises(world_chat.MessageForbiddenError):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id
                ),
            )


def test_same_character_in_two_worlds_has_distinct_scoped_threads() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding_a = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        _, responding_b = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-b",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="b",
        )
        db.commit()

        first = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding_a.id
            ),
        )
        second = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-b",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding_b.id
            ),
        )
        assert first.thread is not None and second.thread is not None
        assert first.thread.id != second.thread.id
        assert [item.id for item in world_chat.list_world_threads(db, owner, "world-a").items] == [
            first.thread.id
        ]
        assert [item.id for item in world_chat.list_world_threads(db, owner, "world-b").items] == [
            second.thread.id
        ]
        with pytest.raises(world_chat.MessageNotFoundError):
            world_chat.get_world_thread(db, owner, "world-a", second.thread.id)


def test_world_chat_requester_cardinality_anomaly_is_not_guessed() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        second_requester_character = _character("second-requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                second_requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()

        # Embedded predecessor corruption/migration anomalies must be detected by
        # code even when the current clean schema normally prevents this state.
        db.execute(text("DROP INDEX uq_world_characters_active_owner_controlled"))
        db.add(
            _world_character(
                "world-a",
                second_requester_character.id,
                owner_id=owner.id,
                suffix="requester-second",
            )
        )
        db.commit()

        result = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert result.outcome == "resolution_required"
        assert result.resolution_code == "requester_cardinality_anomaly"
        assert db.scalar(select(func.count(models.MessageThread.id))) == 0


def test_world_chat_inactive_requester_or_responder_membership_fails_closed() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()

        requester_membership = db.get(models.WorldMembership, "membership-world-a")
        assert requester_membership is not None
        requester_membership.status = "left"
        db.commit()
        with pytest.raises(world_chat.MessageNotFoundError):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id
                ),
            )

        requester_membership.status = "active"
        responder_membership = db.get(
            models.WorldMembership, "membership-world-a-responder"
        )
        assert responder_membership is not None
        responder_membership.status = "left"
        db.commit()
        with pytest.raises(world_chat.MessageNotFoundError):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id
                ),
            )

        assert db.scalar(select(func.count(models.MessageThread.id))) == 0


def test_world_chat_requester_membership_and_character_are_revalidated() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        other = _user("other")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                other,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        db.add_all(
            [
                _world("world-a", owner.id),
                _membership("world-a", owner.id),
                _membership(
                    "world-a",
                    other.id,
                    membership_id="membership-world-a-other",
                    role="member",
                ),
                _membership(
                    "world-a",
                    responder_owner.id,
                    membership_id="membership-world-a-responder",
                    role="member",
                ),
            ]
        )
        db.flush()
        requester = _world_character(
            "world-a",
            requester_character.id,
            owner_id=owner.id,
            membership_id="membership-world-a-other",
            suffix="requester-mismatched-membership",
        )
        responding = _world_character(
            "world-a",
            responding_character.id,
            membership_id="membership-world-a-responder",
            suffix="responding-a",
        )
        db.add_all([requester, responding])
        db.commit()

        mismatched = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert mismatched.outcome == "resolution_required"
        assert mismatched.resolution_code == "requester_missing"

        requester.membership_id = "membership-world-a"
        requester_character.deleted_at = datetime.now(UTC)
        db.commit()
        deleted = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert deleted.outcome == "resolution_required"
        assert deleted.resolution_code == "requester_missing"
        assert db.scalar(select(func.count(models.MessageThread.id))) == 0


def test_world_chat_rejects_requester_when_character_owner_disagrees() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        other_owner = _user("other-owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", other_owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                other_owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()

        result = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )

        assert result.outcome == "resolution_required"
        assert result.resolution_code == "requester_missing"
        assert db.scalar(select(func.count(models.MessageThread.id))) == 0


def test_non_installation_owner_cannot_create_world_chat() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        installation_owner = _user("installation-owner")
        other_owner = _user("other-owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", other_owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                installation_owner,
                other_owner,
                responder_owner,
                _installation(installation_owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=other_owner,
            responder_owner=responder_owner,
            world_id="world-other",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="other",
        )
        db.commit()

        with pytest.raises(world_chat.MessageForbiddenError):
            world_chat.create_or_get_world_thread(
                db,
                other_owner,
                "world-other",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id
                ),
            )
        assert db.scalar(select(func.count(models.MessageThread.id))) == 0


def test_world_chat_unique_conflict_recovers_the_existing_active_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()
        created = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert created.thread is not None

        real_find = world_chat._find_active_world_thread
        calls = 0

        def hide_first_lookup(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return real_find(*args, **kwargs)

        monkeypatch.setattr(world_chat, "_find_active_world_thread", hide_first_lookup)
        replay = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id,
                selected_model="gemini-2.5-flash",
            ),
        )
        assert replay.outcome == "reused"
        assert replay.thread is not None
        assert replay.thread.id == created.thread.id
        assert replay.thread.selected_model == "gemini-2.5-flash"
        assert calls == 2
        assert db.scalar(select(func.count(models.MessageThread.id))) == 1
        db.expire_all()
        persisted = db.get(models.MessageThread, created.thread.id)
        assert persisted is not None
        assert persisted.selected_model == "gemini-2.5-flash"


def test_world_chat_first_preference_unique_conflict_retries_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()

        real_ensure = world_chat.ensure_user_preference
        calls = 0

        def fail_first_preference_flush(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise world_chat.IntegrityError(
                    "concurrent preference winner",
                    {},
                    RuntimeError("UNIQUE constraint failed: user_message_preferences.user_id"),
                )
            return real_ensure(*args, **kwargs)

        monkeypatch.setattr(
            world_chat, "ensure_user_preference", fail_first_preference_flush
        )
        created = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )

        assert created.outcome == "created"
        assert created.thread is not None
        assert calls == 2
        assert db.scalar(select(func.count(models.UserMessagePreference.user_id))) == 1
        assert db.scalar(select(func.count(models.MessageThread.id))) == 1


def test_world_chat_stale_membership_is_not_listed_or_read() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()
        created = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert created.thread is not None

        responder_membership = db.get(
            models.WorldMembership, "membership-world-a-responder"
        )
        assert responder_membership is not None
        responder_membership.status = "left"
        db.commit()

        assert world_chat.list_world_threads(db, owner, "world-a").items == []
        with pytest.raises(world_chat.MessageNotFoundError):
            world_chat.get_world_thread(db, owner, "world-a", created.thread.id)


def test_world_chat_precommit_revalidation_failure_rolls_back_all_new_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()

        def fail_revalidation(*_args, **_kwargs):
            raise world_chat.MessageForbiddenError("injected precommit denial")

        monkeypatch.setattr(world_chat, "_world_thread_read", fail_revalidation)
        with pytest.raises(
            world_chat.MessageForbiddenError, match="injected precommit denial"
        ):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id
                ),
            )

        assert db.scalar(select(func.count(models.MessageThread.id))) == 0
        assert db.scalar(select(func.count(models.UserMessagePreference.user_id))) == 0


def test_world_chat_reused_thread_model_change_rolls_back_on_revalidation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()
        created = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert created.thread is not None
        thread_id = created.thread.id

        def fail_revalidation(*_args, **_kwargs):
            raise world_chat.MessageForbiddenError("injected precommit denial")

        monkeypatch.setattr(world_chat, "_world_thread_read", fail_revalidation)
        with pytest.raises(
            world_chat.MessageForbiddenError, match="injected precommit denial"
        ):
            world_chat.create_or_get_world_thread(
                db,
                owner,
                "world-a",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id,
                    selected_model="gemini-2.5-flash",
                ),
            )

        db.expire_all()
        thread = db.get(models.MessageThread, thread_id)
        assert thread is not None
        assert thread.selected_model == world_chat.DEFAULT_MESSAGE_MODEL


def test_resolved_world_thread_legacy_api_is_redirect_only_and_not_mutable() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        responder_owner = _user("responder-owner")
        requester_character = _character("requester-character", owner.id)
        responding_character = _character("responding-character", responder_owner.id)
        db.add_all(
            [
                owner,
                responder_owner,
                _installation(owner.id),
                requester_character,
                responding_character,
            ]
        )
        db.flush()
        _, responding = _seed_world(
            db,
            owner=owner,
            responder_owner=responder_owner,
            world_id="world-a",
            requester_character=requester_character,
            responding_character=responding_character,
            suffix="a",
        )
        db.commit()
        created = world_chat.create_or_get_world_thread(
            db,
            owner,
            "world-a",
            schemas.WorldChatThreadCreate(
                responding_world_character_id=responding.id
            ),
        )
        assert created.thread is not None
        thread_id = created.thread.id
        db.add(
            models.MessageMessage(
                thread_id=thread_id,
                role="user",
                content="legacy endpoint에 노출되면 안 되는 원문",
                model=world_chat.DEFAULT_MESSAGE_MODEL,
                status="ok",
            )
        )
        db.commit()

        legacy_detail = world_chat.get_thread(db, owner, thread_id)
        assert legacy_detail.world_scope_status == "resolved"
        assert legacy_detail.world_id == "world-a"
        assert legacy_detail.messages == []
        assert legacy_detail.latest_message is None
        legacy_list_item = world_chat.list_threads(db, owner).items[0]
        assert legacy_list_item.messages == []
        assert legacy_list_item.latest_message is None

        with pytest.raises(
            world_chat.MessageValidationError,
            match="해당 World Chat에서만 변경",
        ):
            world_chat.update_thread(
                db,
                owner,
                thread_id,
                schemas.MessageThreadUpdate(selected_model="gemini-2.5-flash"),
            )
        with pytest.raises(world_chat.MessageValidationError):
            world_chat.delete_thread(db, owner, thread_id)
        with pytest.raises(world_chat.MessageValidationError):
            asyncio.run(
                world_chat.send_message(
                    db,
                    owner,
                    thread_id,
                    schemas.MessageMessageCreate(content="legacy send 차단"),
                )
            )
        with pytest.raises(world_chat.MessageValidationError):
            asyncio.run(world_chat.retry_message(db, owner, thread_id, 1))

        db.expire_all()
        thread = db.get(models.MessageThread, thread_id)
        assert thread is not None
        assert thread.deleted_at is None
        assert thread.selected_model == world_chat.DEFAULT_MESSAGE_MODEL
        assert db.scalar(select(func.count(models.MessageMessage.id))) == 1


def test_claimed_local_installation_rejects_new_unscoped_legacy_thread() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as db:
        owner = _user("owner")
        target = _character("legacy-target", owner.id)
        target.execution_mode = "llm"
        db.add_all([owner, _installation(owner.id), target])
        db.commit()

        with pytest.raises(
            world_chat.MessageValidationError,
            match="World Chat에서 시작",
        ):
            world_chat.create_or_get_thread(
                db,
                owner,
                schemas.MessageThreadCreate(character_id=target.id),
            )

        assert db.scalar(select(func.count(models.MessageThread.id))) == 0
        assert db.scalar(select(func.count(models.UserMessagePreference.user_id))) == 0


def test_lock_safe_preference_creation_flushes_without_committing() -> None:
    calls: list[str] = []

    class FakeSession:
        def get(self, _model, _key):
            calls.append("get")
            return None

        def add(self, _value) -> None:
            calls.append("add")

        def flush(self) -> None:
            calls.append("flush")

        def commit(self) -> None:
            calls.append("commit")

        def refresh(self, _value) -> None:
            calls.append("refresh")

    preference = world_chat.ensure_user_preference(
        FakeSession(),  # type: ignore[arg-type]
        SimpleNamespace(id="owner"),  # type: ignore[arg-type]
        commit_if_created=False,
    )

    assert preference.user_id == "owner"
    assert calls == ["get", "add", "flush"]
