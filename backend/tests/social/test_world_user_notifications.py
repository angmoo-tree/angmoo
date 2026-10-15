"""World notifications through canonical writes, real SQLite and actual HTTP routes."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from model_fixture_support import models
from social.test_l4_social_write_uow import _session_factory, _owner_post, _autonomous_post
from app.domains.social import dependencies
from app.domains.social.contracts.writes import OwnerReplyCommand
from app.domains.social.service.world_notifications import WorldNotificationService
from app.domains.social.service.world_notification_delivery import deliver_world_notification
from app.domains.social.contracts.world_notifications import WorldNotificationError
from app.domains.social.router_world_notifications import router
from app.runtime.social.composition import configure_social_runtime
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
from app.runtime.social.world_notification_references import RuntimeWorldNotificationReferences

WORLD, USER, ME, ACTOR = "social-uow-world", "social-uow-owner", "social-uow-owner-actor", "social-uow-autonomous-actor"


@pytest.fixture
def factory(tmp_path):
    value = _session_factory(tmp_path)
    try:
        yield value
    finally:
        value.kw["bind"].dispose()


def service(db):
    return WorldNotificationService(db, RuntimeWorldNotificationReferences(db))


def owner_post(factory):
    with factory() as db:
        return SqlAlchemySocialWriteUnitOfWork(db).create_owner_post(_owner_post()).post.id


def reply(factory, target, key="notification-reply"):
    with factory() as db:
        command = replace(_autonomous_post(), operation="reply", target_post_id=target, body="A visible reply", idempotency_key=key)
        return SqlAlchemySocialWriteUnitOfWork(db).apply_validated_autonomous_result(command).post.id


def notification_ids(factory):
    with factory() as db:
        return [item.id for item in service(db).page(world_id=WORLD, user_id=USER).items]


def clone_world_profiles(factory, world_id, *, owner_id=None):
    """Independent World registrations, reusing only initial character originals."""
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    with factory() as db:
        template = db.get(models.World, WORLD)
        values = {col.key: getattr(template, col.key) for col in models.World.__table__.columns if col.key not in {"id", "slug", "create_idempotency_key"}}
        db.add(models.World(id=world_id, slug=world_id, create_idempotency_key=world_id, **values))
        db.flush()
        member_id = f"member-{world_id}"
        db.add(models.WorldMembership(id=member_id, world_id=world_id, user_id=USER, role="owner", status="active"))
        db.add(models.WorldRole(id=f"role-{world_id}", world_id=world_id, role_key="resident", name="Resident", description="fixture", responsibilities=[], allowed_activity_scope=[], autonomous_allowed=True, status="enabled"))
        db.flush()
        for source_id, target_id in ((ME, owner_id or f"owner-{world_id}"), (ACTOR, f"mango-{world_id}")):
            source, configuration = db.get(models.WorldCharacter, source_id), db.get(WorldCharacterConfiguration, source_id)
            values = {col.key: getattr(source, col.key) for col in models.WorldCharacter.__table__.columns if col.key not in {"id", "world_id", "membership_id"}}
            db.add(models.WorldCharacter(id=target_id, world_id=world_id, membership_id=member_id, **values))
            db.flush()
            db.add(WorldCharacterConfiguration(world_character_id=target_id, snapshot_id=configuration.snapshot_id, profile=configuration.profile, settings=configuration.settings))
        db.commit()


def seed_world_activity(factory, world_id, *, key):
    with factory() as db:
        for original, target in ((ME, f"owner-{world_id}"), (ACTOR, f"mango-{world_id}")):
            source = db.get(models.WorldCharacter, original)
            db.get(models.CharacterActiveWorld, source.character_id).world_character_id = target
        db.commit()
        post = SqlAlchemySocialWriteUnitOfWork(db).create_owner_post(replace(_owner_post(), world_id=world_id, idempotency_key=f"owner-{key}"))
    with factory() as db:
        result = SqlAlchemySocialWriteUnitOfWork(db).apply_validated_autonomous_result(replace(_autonomous_post(),
            world_id=world_id, actor_world_character_id=f"mango-{world_id}", operation="reply", target_post_id=post.post.id,
            idempotency_key=f"reply-{key}", body=f"A real committed reply in {world_id}"))
    return result.post.id


def canonical_feed_like(db, post_id, signature, *, action="like"):
    """The actual timeline source plus World Feed successful-event owner."""
    from app.core.unit_of_work import deferred_commits
    from app.domains.social.schemas.community import PostLikeCreate
    from app.domains.social.schemas.feed import WorldFeedCandidateRead, FeedReactionDecision
    from app.runtime.social.timeline import timeline_service
    from app.runtime.social.world_feed_actions import apply_successful_world_feed_action
    post = db.get(models.Post, post_id)
    actor = db.get(models.WorldCharacter, ACTOR)
    run = models.AgentRun(id=f"run-{signature}", user_id=USER, character_id=actor.character_id,
        agent_id="notification-fixture", session_key=signature, status="running")
    db.add(run)
    db.flush()
    execution = models.AgentPublicActionExecution(run_id=run.id, character_id=actor.character_id,
        signature=signature, scope="world_feed", action_type=action, target_post_id=post_id,
        world_id=WORLD, actor_world_character_id=actor.id, status="succeeded")
    db.add(execution)
    db.flush()
    candidate = WorldFeedCandidateRead(candidate_index=0, post_id=post_id,
        author_world_character_id=post.author_world_character_id, author_character_id=post.author_character_id,
        author_name=post.author_name, title=post.title, body_preview=post.body, topic_signature="fixture",
        created_at=post.created_at, world_local_datetime="2026-10-15T12:00:00+09:00", age_seconds=0,
        age_bucket="recent", matched_keywords=[], matched_fields=[], rank_score=1, allowed_actions=[action])
    with deferred_commits():
        user = db.get(models.User, USER)
        if action == "follow":
            from app.domains.social.service.profiles import follow_profile
            from app.domains.social.schemas.community import FollowCreate
            follow_profile(db, user, FollowCreate(follower_character_id=actor.character_id, target_type="character", target_id=post.author_character_id))
        elif action == "repost":
            timeline_service.repost_post(db, user, post_id, PostLikeCreate(character_id=actor.character_id))
        else:
            timeline_service.like_post(db, user, post_id, PostLikeCreate(character_id=actor.character_id))
        result = apply_successful_world_feed_action(db,
            profile=SimpleNamespace(world=db.get(models.World, WORLD), character=db.get(models.Character, actor.character_id), world_character=actor),
            candidate=candidate, decision=FeedReactionDecision(selected_candidate_index=0, selected_action=action, brief="A bounded fixture reaction."), draft=None,
            action_result={}, execution=execution, occurred_at=datetime.now(UTC))
    db.commit()
    return result.event.id


@pytest.mark.parametrize("action", ["repost", "follow"])
def test_other_canonical_reactions_create_one_scoped_delivery_and_follow_capability(factory, action):
    post_id = owner_post(factory)
    with factory() as db:
        canonical_feed_like(db, post_id, f"actual-{action}", action=action)
        page = service(db).page(world_id=WORLD, user_id=USER)
        assert page.unread_count == 1 and len(page.items) == 1
        assert page.items[0].notification_type == action
        assert db.scalar(select(func.count(models.Notification.id)).where(models.Notification.world_id == WORLD)) == 1
        if action == "follow":
            assert page.items[0].target.world_character_id == ACTOR
            db.get(models.Character, "social-uow-autonomous-character").deleted_at = datetime.now(UTC)
            db.commit()
            assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 0
        else:
            db.delete(db.scalar(select(models.PostRepost)))
            db.commit()
            assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 0


def test_actual_quote_and_effective_handle_mentions(factory):
    from app.domains.social.schemas.community import TimelineQuoteCreate
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    from app.runtime.social.timeline import timeline_service
    from app.core.unit_of_work import deferred_commits
    post_id = owner_post(factory)
    with factory() as db:
        configuration = db.get(WorldCharacterConfiguration, ME)
        configuration.profile = {**configuration.profile, "handle": "only_here"}
        db.commit()
        with deferred_commits():
            quote = timeline_service.create_quote(db, db.get(models.User, USER), post_id,
                TimelineQuoteCreate(body="A real quote", author_character_id="social-uow-autonomous-character"))
        db.commit()
    with factory() as db:
        mention = SqlAlchemySocialWriteUnitOfWork(db).apply_validated_autonomous_result(replace(_autonomous_post(),
            body="Hello @only_here", idempotency_key="mention-effective-handle"))
        page = service(db).page(world_id=WORLD, user_id=USER)
        assert {item.notification_type for item in page.items} == {"quote", "mention"}
        assert {item.target.post_id for item in page.items} == {quote.id, mention.post.id}
        assert page.unread_count == 2


def test_concurrent_same_source_replay_delivers_once(factory):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    post_id, barrier = owner_post(factory), Barrier(2)
    def execute():
        barrier.wait(timeout=5)
        return reply(factory, post_id, key="concurrent-same-reply")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(execute), pool.submit(execute)
        assert first.result(timeout=15) == second.result(timeout=15)
    with factory() as db:
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 1
        assert db.scalar(select(func.count(models.Notification.id))) == 1


def test_current_profile_switch_and_unconfigured_profile_do_not_reuse_old_delivery(factory):
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    post_id = owner_post(factory)
    reply(factory, post_id)
    with factory() as db:
        prior = service(db).page(world_id=WORLD, user_id=USER, limit=1)
        mine = db.get(models.WorldCharacter, ME)
        mine.status = "inactive"
        db.commit()
        assert service(db).batch(world_ids=[WORLD], user_id=USER).items[0].status == "unavailable"
        with pytest.raises(WorldNotificationError):
            service(db).count(world_id=WORLD, user_id=USER)
        from social.test_l4_social_write_uow import _character
        db.add(_character("replacement-user-character", USER, "Replacement User"))
        db.flush()
        replacement = models.WorldCharacter(id="replacement-user-profile", world_id=WORLD,
            character_id="replacement-user-character", membership_id=mine.membership_id,
            role_key=mine.role_key, status="active", control_mode="owner_controlled", owner_user_id=USER,
            autonomous_enabled=False, character_contract_hash=mine.character_contract_hash, world_contract_hash=mine.world_contract_hash)
        db.add(replacement)
        db.flush()
        original = db.get(WorldCharacterConfiguration, ME)
        db.add(WorldCharacterConfiguration(world_character_id=replacement.id, snapshot_id=original.snapshot_id, profile=original.profile, settings=original.settings))
        db.commit()
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 0
        with pytest.raises(WorldNotificationError):
            service(db).mark_read(world_id=WORLD, user_id=USER, notification_id=prior.items[0].id)
        assert db.get(models.Notification, prior.items[0].id).read_at is None


@pytest.mark.parametrize("profile", ["full", "public"])
def test_official_app_route_registration_and_same_session_factory(factory, profile):
    from app import main
    app = main.create_app(profile=profile, prepare_media_directories=False)
    with factory() as db:
        statements = []
        def record(*args): statements.append(args[2])
        event.listen(db.get_bind(), "before_cursor_execute", record)
        instance = app.state.social_world_notification_factory(db)
        assert instance.db is db and instance.references.db is db and statements == []
        event.remove(db.get_bind(), "before_cursor_execute", record)
    paths = {(path, method.upper()) for path, operations in app.openapi()["paths"].items() for method in operations}
    assert ("/api/v1/worlds/{world_id}/notifications", "GET") in paths
    assert ("/api/v1/worlds/{world_id}/notifications/{notification_id}/read", "PATCH") in paths
    assert ("/api/v1/notifications/world-unread-counts", "GET") in paths


def test_real_world_erasure_removes_only_that_scoped_delivery_and_keeps_originals(factory, tmp_path):
    from app.domains.characters.models_import import CharacterImportSnapshot
    from app.domains.worlds.service.deletion import accept
    from app.domains.worlds.contracts_deletion import WorldDeletionCommand
    from app.runtime.world_deletion.canonical_erasure import ScopedWorldErasure, stop_admission
    from app.runtime.world_deletion.worker import WorldDeletionWorker
    clone_world_profiles(factory, "other-notification-world")
    seed_world_activity(factory, "other-notification-world", key="other-world")
    # Return the autonomous character to its first World before its next source write.
    with factory() as db:
        db.get(models.CharacterActiveWorld, "social-uow-autonomous-character").world_character_id = ACTOR
        db.commit()
    post_id = owner_post(factory)
    reply(factory, post_id)
    with factory() as db:
        originals = list(db.execute(select(CharacterImportSnapshot.id, CharacterImportSnapshot.digest)))
        receipt = accept(db, WORLD, USER, WorldDeletionCommand(expected_row_version=1,
            confirmed_name=db.get(models.World, WORLD).name, consent=True, idempotency_key="notification-delete-world"), stop_admission=stop_admission)
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    with factory() as db, pytest.raises(IntegrityError, match="world_deleting"):
        db.execute(update(models.Notification).where(models.Notification.world_id == WORLD).values(delivery_key="a" * 64))
    worker = WorldDeletionWorker(factory, ScopedWorldErasure(tmp_path / "media", index_cleanup=lambda _: None, graph_cleanup=lambda _: None))
    for _ in range(500):
        worker.tick()
        with factory() as db:
            result = db.get(models.WorldDeletionRequest, receipt.request_id)
            if result.state in {"completed", "failed"}:
                assert result.state == "completed", (result.stage, result.failure_code)
                break
    else:
        pytest.fail("World erasure did not settle")
    with factory() as db:
        assert db.scalar(select(func.count(models.Notification.id)).where(models.Notification.world_id == WORLD)) == 0
        assert service(db).count(world_id="other-notification-world", user_id=USER).unread_count == 1
        assert list(db.execute(select(CharacterImportSnapshot.id, CharacterImportSnapshot.digest))) == originals
        assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_real_feed_like_lifetime_uses_new_event_not_reused_reaction_row_id(factory):
    post_id = owner_post(factory)
    with factory() as db:
        first_event = canonical_feed_like(db, post_id, "like-first")
        first = service(db).page(world_id=WORLD, user_id=USER)
        assert first.unread_count == 1 and first.items[0].notification_type == "like"
        first_row = db.get(models.Notification, first.items[0].id)
        assert first_row.source_social_event_id == first_event
        first_reaction_id = db.scalar(select(models.PostLike.id))
        db.delete(db.get(models.PostLike, first_reaction_id))
        db.commit()
        assert not service(db).page(world_id=WORLD, user_id=USER).items
        second_event = canonical_feed_like(db, post_id, "like-second")
        assert second_event != first_event
        second = service(db).page(world_id=WORLD, user_id=USER)
        assert second.unread_count == 1 and len(second.items) == 1
        assert second.items[0].id != first_row.id
        assert db.scalar(select(func.count(models.Notification.id))) == 2
        # Both historical rows remain; only the new live reaction is eligible.
        assert db.get(models.Notification, first_row.id).source_social_event_id == first_event


def test_delivery_is_atomic_idempotent_and_preserves_the_first_read(factory):
    post_id = owner_post(factory)
    def fail(stage):
        if stage == "before_commit":
            raise RuntimeError("controlled_notification_rollback")
    with factory() as db:
        before_posts = db.scalar(select(func.count(models.Post.id)))
        command = replace(_autonomous_post(), operation="reply", target_post_id=post_id, idempotency_key="rollback-reply")
        with pytest.raises(RuntimeError, match="controlled_notification_rollback"):
            SqlAlchemySocialWriteUnitOfWork(db, failure_injector=fail).apply_validated_autonomous_result(command)
        assert db.scalar(select(func.count(models.Notification.id))) == 0
        assert db.scalar(select(func.count(models.Post.id))) == before_posts
        result = SqlAlchemySocialWriteUnitOfWork(db).apply_validated_autonomous_result(command)
        row = db.scalar(select(models.Notification))
        first_read = service(db).mark_read(world_id=WORLD, user_id=USER, notification_id=row.id).read_at
        arguments = dict(world_id=WORLD, recipient_world_character_id=ME, recipient_character_id="social-uow-owner-character",
            actor_world_character_id=ACTOR, actor_character_id="social-uow-autonomous-character", notification_type="reply",
            source_kind="post", source_id=result.post.id, post_id=post_id, source_post_id=result.post.id)
        assert deliver_world_notification(db, **arguments).read_at == first_read
        with pytest.raises(ValueError, match="notification_delivery_conflict"):
            deliver_world_notification(db, **{**arguments, "post_id": result.post.id})
        assert db.scalar(select(func.count(models.Notification.id))) == 1


def test_batch_scale_query_count_profile_isolation_and_deleting_world(factory):
    import json
    from pathlib import Path
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    from app.domains.social.repository.world_notifications import eligible
    from app.domains.worlds.models_deletion import WorldDeletionRequest
    with factory() as db:
        template = db.get(models.World, WORLD)
        original_actor = db.get(models.WorldCharacter, ME)
        original_configuration = db.get(WorldCharacterConfiguration, ME)
        ids = [WORLD]
        for index in range(1, 50):
            world_id = f"notification-world-{index}"
            values = {col.key: getattr(template, col.key) for col in models.World.__table__.columns if col.key not in {"id", "slug", "create_idempotency_key"}}
            db.add(models.World(id=world_id, slug=world_id, create_idempotency_key=world_id, **values))
            db.flush()
            member_id, role_id = f"notification-member-{index}", f"notification-owner-{index}"
            db.add(models.WorldMembership(id=member_id, world_id=world_id, user_id=USER, role="owner", status="active"))
            db.flush()
            db.add(models.WorldCharacter(id=role_id, world_id=world_id, character_id=original_actor.character_id,
                membership_id=member_id, role_key=None, status="active", control_mode="owner_controlled", owner_user_id=USER,
                autonomous_enabled=False, character_contract_hash=original_actor.character_contract_hash,
                world_contract_hash=original_actor.world_contract_hash))
            db.flush()
            db.add(WorldCharacterConfiguration(world_character_id=role_id, snapshot_id=original_configuration.snapshot_id,
                profile=original_configuration.profile, settings=original_configuration.settings))
            ids.append(world_id)
        db.commit()
        statements = []
        def record(*args):
            statements.append(args[2])
        event.listen(db.get_bind(), "before_cursor_execute", record)
        five = service(db).batch(world_ids=ids[:5], user_id=USER)
        five_count = len(statements)
        statements.clear()
        fifty = service(db).batch(world_ids=ids, user_id=USER)
        fifty_count = len(statements)
        event.remove(db.get_bind(), "before_cursor_execute", record)
        assert len(five.items) == 5 and len(fifty.items) == 50
        assert all(item.status == "available" and item.unread_count == 0 for item in fifty.items)
        assert five_count == fifty_count
        assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements)
        scopes = RuntimeWorldNotificationReferences(db).scopes(world_ids=ids, user_id=USER)
        query = eligible(list(scopes.values()), set())
        sql = str(query.compile(db.get_bind(), compile_kwargs={"literal_binds": True}))
        plan = [list(row) for row in db.connection().exec_driver_sql("EXPLAIN QUERY PLAN " + sql)]
        assert any("ix_notifications_world_recipient_id" in str(row) for row in plan)
        artifact = Path(__file__).resolve().parents[3] / "artifacts/world-user-notifications-20261015/batch-query-evidence.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"five_world_queries": five_count, "fifty_world_queries": fifty_count, "query_plan": plan}, indent=2), encoding="utf-8")
        db.add(WorldDeletionRequest(id="notification-delete", world_id=ids[1], owner_id=USER,
            idempotency_key="a"*64, confirmation_digest="b"*64, state="accepted"))
        db.commit()
        result = service(db).batch(world_ids=[WORLD, ids[1], "unknown-world"], user_id=USER)
        assert [row.status for row in result.items] == ["available", "unavailable", "unavailable"]
        assert service(db).batch(world_ids=[WORLD], user_id="unrelated-user").items[0].unread_count is None


def test_canonical_reply_replay_scope_and_read_do_not_change_activity(factory):
    post_id = owner_post(factory)
    source = reply(factory, post_id)
    assert reply(factory, post_id) == source
    with factory() as db:
        page = service(db).page(world_id=WORLD, user_id=USER)
        assert page.unread_count == 1 and len(page.items) == 1
        item = page.items[0]
        assert item.target.post_id == source and item.actor_world_character_id == ACTOR
        row = db.get(models.Notification, item.id)
        assert row.recipient_world_character_id == ME and row.delivery_key
        assert row.source_social_event_id is not None
        assert row.read_at is None and row.handled_at is None
        event_count = db.scalar(select(func.count(models.SocialEvent.id)))
        result = service(db).mark_read(world_id=WORLD, user_id=USER, notification_id=item.id)
        again = service(db).mark_read(world_id=WORLD, user_id=USER, notification_id=item.id)
        assert result.read_at == again.read_at and result.unread_count == again.unread_count == 0
        assert row.handled_at is None and row.handling_outcome is None
        assert db.scalar(select(func.count(models.SocialEvent.id))) == event_count
        assert len(service(db).page(world_id=WORLD, user_id=USER).items) == 1


def test_reply_to_my_reply_not_original_author(factory):
    with factory() as db:
        root = SqlAlchemySocialWriteUnitOfWork(db).apply_validated_autonomous_result(_autonomous_post()).post.id
    with factory() as db:
        mine = SqlAlchemySocialWriteUnitOfWork(db).create_owner_reply(OwnerReplyCommand(WORLD, USER, "owner-reply", root, "My own reply")).post.id
    # The current validated autonomous writer admits root targets. The actual
    # timeline+canonical action linker supports replies to replies as well.
    from app.runtime.social.timeline import timeline_service
    from app.core.unit_of_work import deferred_commits
    with factory() as db:
        with deferred_commits():
            from app.domains.social.schemas.community import TimelineReplyCreate
            result = timeline_service.create_reply(db, db.get(models.User, USER), mine,
                TimelineReplyCreate(body="Reply to your reply", author_character_id="social-uow-autonomous-character"), enforce_user_quota=False)
        db.commit()
        page = service(db).page(world_id=WORLD, user_id=USER)
        assert page.unread_count == 1
        assert page.items[0].target.post_id == result.id
        row = db.get(models.Notification, page.items[0].id)
        assert row.post_id == mine and row.recipient_world_character_id == ME


def test_visibility_blocks_legacy_and_source_deletion_share_count_predicate(factory):
    post_id = owner_post(factory)
    source = reply(factory, post_id)
    with factory() as db:
        # Unknown legacy scope is preserved, never inferred as this user's World.
        legacy = models.Notification(notification_type="reply", recipient_character_id="social-uow-owner-character",
            actor_character_id="social-uow-autonomous-character", post_id=post_id, source_post_id=source)
        db.add(legacy)
        db.commit()
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 1
        db.get(models.Post, source).visibility = "private"
        db.commit()
        assert service(db).page(world_id=WORLD, user_id=USER).unread_count == 0
        assert not service(db).page(world_id=WORLD, user_id=USER).items
        db.get(models.Post, source).visibility = "public"
        for field in ("deleted_at", "report_hidden_at"):
            setattr(db.get(models.Post, source), field, datetime.now(UTC))
            db.commit()
            assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 0
            assert service(db).page(world_id=WORLD, user_id=USER).items == []
            setattr(db.get(models.Post, source), field, None)
            db.commit()
        db.add(models.WorldCharacterBlock(id="notification-block", world_id=WORLD, blocker_world_character_id=ME, blocked_world_character_id=ACTOR))
        db.commit()
        assert service(db).count(world_id=WORLD, user_id=USER).unread_count == 0
        assert db.get(models.Notification, legacy.id).world_id is None


def test_exact_count_pagination_scoped_cursor_and_no_read_on_get(factory):
    post_id = owner_post(factory)
    with factory() as db:
        for index in range(101):
            source = models.Post(id=f"notification-source-{index}", world_id=WORLD, author_world_character_id=ACTOR,
                author_character_id="social-uow-autonomous-character", author_name="Mango", title="Reply", body="Body",
                post_type="reply", visibility="public", reply_to_post_id=post_id)
            db.add(source)
            db.flush()
            deliver_world_notification(db, world_id=WORLD, recipient_world_character_id=ME,
                recipient_character_id="social-uow-owner-character", actor_world_character_id=ACTOR,
                actor_character_id="social-uow-autonomous-character", notification_type="reply",
                source_kind="post", source_id=source.id, post_id=post_id, source_post_id=source.id)
        db.commit()
        statements = []
        event.listen(db.get_bind(), "before_cursor_execute", lambda *args: statements.append(args[2]))
        first = service(db).page(world_id=WORLD, user_id=USER)
        second = service(db).page(world_id=WORLD, user_id=USER, cursor=first.next_cursor)
        assert len(first.items) == len(second.items) == 20 and first.unread_count == second.unread_count == 101
        assert not ({item.id for item in first.items} & {item.id for item in second.items})
        assert not any(sql.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for sql in statements)
        assert db.scalar(select(func.count(models.Notification.id)).where(models.Notification.read_at.is_not(None))) == 0
        with pytest.raises(WorldNotificationError):
            service(db).page(world_id=WORLD, user_id=USER, cursor="invalid")


def test_real_http_batch_partial_scope_and_id_tampering(factory, monkeypatch):
    from social.test_l4_social_write_uow import _user
    with factory() as db:
        db.add(_user("other-user"))
        db.commit()
    post_id = owner_post(factory)
    reply(factory, post_id)
    app = FastAPI()
    configure_social_runtime(app)
    app.include_router(router, prefix="/api/v1")
    def db_dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[dependencies.get_db] = db_dependency
    app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id=USER)
    with TestClient(app, base_url="http://127.0.0.1:3000", headers={"Origin": "http://127.0.0.1:3000"}) as client:
        base = f"/api/v1/worlds/{WORLD}/notifications"
        page = client.get(base).json()
        assert page["unread_count"] == 1
        assert page["items"][0]["created_at"].endswith("Z")
        single = client.get(base + "/unread-count")
        assert single.status_code == 200 and single.json()["unread_count"] == 1
        batch = client.get("/api/v1/notifications/world-unread-counts", params=[("world_ids", WORLD), ("world_ids", "other-private-world"), ("world_ids", WORLD)])
        assert batch.status_code == 200
        assert batch.json()["items"] == [dict(world_id=WORLD, recipient_world_character_id=ME, status="available", unread_count=1),
            dict(world_id="other-private-world", recipient_world_character_id=None, status="unavailable", unread_count=None)]
        assert client.get("/api/v1/notifications/world-unread-counts", params=[("world_ids", f"world-{i}") for i in range(51)]).status_code == 422
        assert client.patch(base + "/999999/read").status_code == 404
        from app.domains.social import router_world_notifications as http
        from app.core.sqlite_concurrency import SqliteRetryPolicy
        real_runner = http.run_sqlite_session_immediate
        monkeypatch.setattr(http, "run_sqlite_session_immediate", lambda db, operation: real_runner(db, operation,
            retry_policy=SqliteRetryPolicy(maximum_elapsed_seconds=0.02)))
        with factory.kw["bind"].connect() as blocker:
            blocker.exec_driver_sql("BEGIN IMMEDIATE")
            busy = client.patch(base + f'/{page["items"][0]["id"]}/read')
            assert busy.status_code == 503 and busy.json()["detail"] == "sqlite_busy_retry_exhausted"
            assert client.get(base).json()["unread_count"] == 1
            blocker.rollback()
        read = client.patch(base + f'/{page["items"][0]["id"]}/read')
        assert read.status_code == 200 and read.json()["unread_count"] == 0
        assert read.json()["read_at"].endswith("Z")
        assert client.get(base).json()["items"][0]["read_at"] is not None
        with factory() as db:
            root = SqlAlchemySocialWriteUnitOfWork(db).apply_validated_autonomous_result(replace(_autonomous_post(), idempotency_key="http-other-root")).post.id
            mine = SqlAlchemySocialWriteUnitOfWork(db).create_owner_reply(OwnerReplyCommand(WORLD, USER, "http-my-reply", root, "My reply to another author's original")).post.id
            canonical_feed_like(db, mine, "http-like-my-reply")
        nested = client.get(base).json()
        like = next(item for item in nested["items"] if item["notification_type"] == "like")
        assert like["target"]["post_id"] == mine and nested["unread_count"] == 1
        assert client.patch(base + f'/{like["id"]}/read').json()["unread_count"] == 0
        assert client.get(base, headers={"Origin": "https://external.invalid", "Host": "external.invalid"}).status_code == 403
        assert client.patch(base + "/999999/read", headers={"Origin": "https://external.invalid"}).status_code == 403
        app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id="other-user")
        assert client.get(base).status_code == 404
        assert client.patch(base + f'/{page["items"][0]["id"]}/read').status_code == 404
