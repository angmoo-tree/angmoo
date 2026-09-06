from datetime import UTC, datetime, timedelta
from dataclasses import replace

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import models
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.runtime.routine_posts.interactions import CanonicalRoutineInteractionSource
from app.runtime.routine_posts.interactions import RuntimeRoutineInteractionReferences
from relationships.test_social_event_runtime import _engine, _seed, _post, _record_post_event


def test_routine_interactions_keep_cutoff_direction_pending_block_and_caller_rollback():
    engine = _engine()
    current = datetime(2026, 8, 11, 5, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        target = _post(
            db,
            post_id="interaction-read-root",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="A shared question",
        )
        replies = []
        events = []
        for index in range(2):
            reply = _post(
                db,
                post_id=f"interaction-read-reply-{index}",
                author=fixture.actor,
                author_world_character=fixture.actor_world_character,
                body=f"Answer {index}",
                reply_to_post_id=target.id,
            )
            replies.append(reply)
            result = _record_post_event(
                db,
                fixture=fixture,
                event_idempotency=f"interaction-read-{index}",
                source=reply,
                target_post=target,
                event_type="comment_created",
                actor_world_character_id=fixture.actor_world_character.id,
                target_world_character_id=fixture.target_world_character.id,
                comment_purpose="encouragement",
                occurred_at=current + timedelta(seconds=index),
            )
            events.append(result.event)
        reverse = models.RelationshipState(
            id="interaction-read-reverse",
            world_id=fixture.world.id,
            actor_world_character_id=fixture.target_world_character.id,
            target_world_character_id=fixture.actor_world_character.id,
            trust=45,
            affinity=35,
            familiarity=50,
        )
        db.add(reverse)
        db.commit()
        commits = []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        source = CanonicalRoutineInteractionSource()
        args = dict(
            world_id=fixture.world.id,
            consumer_world_character_id=fixture.target_world_character.id,
            episode_id="unrelated-episode",
            after=current - timedelta(seconds=1),
            before=current + timedelta(seconds=1),
        )
        found = source.candidates(db, **args)
        assert all(type(item) is RoutineInteractionInput for item in found)
        assert [item.source_event_id for item in found] == [item.id for item in events]
        assert [item.relationship_band for item in found] == ["trusted", "trusted"]
        assert [item.episode_relevance for item in found] == [60, 60]
        assert source.references.get_post(db, replies[0].id) is replies[0]
        assert [
            item.source_event_id
            for item in source.candidates(db, **{**args, "after": current})
        ] == [events[1].id]
        reverse.trust = 0
        reverse.affinity = 0
        reverse.familiarity = 10
        assert [item.relationship_band for item in source.candidates(db, **args)] == [
            "familiar",
            "familiar",
        ]
        db.add(
            models.WorldCharacterBlock(
                id="interaction-read-block",
                world_id=fixture.world.id,
                blocker_world_character_id=fixture.actor_world_character.id,
                blocked_world_character_id=fixture.target_world_character.id,
            )
        )
        assert source.candidates(db, **args) == []
        assert commits == []
        db.rollback()
        assert [
            replace(item, occurred_at=item.occurred_at.replace(tzinfo=UTC))
            for item in source.candidates(db, **args)
        ] == found
        assert reverse.trust == 45
        assert db.get(models.WorldCharacterBlock, "interaction-read-block") is None
        assert commits == []
    engine.dispose()


def test_interaction_source_lookup_keeps_unfiltered_identity_map_and_lazy_sql():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(
            db,
            post_id="interaction-raw-lookup",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="Stored evidence",
        )
        db.commit()
        post_id = post.id
        post.deleted_at = datetime(2026, 8, 11, tzinfo=UTC)
        post.report_hidden_at = datetime(2026, 8, 11, tzinfo=UTC)
        statements = []
        flushes = []
        event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
        event.listen(db, "before_flush", lambda *_: flushes.append("flush"))
        references = RuntimeRoutineInteractionReferences()

        # Evidence validation owns visibility checks after the original db.get.
        assert references.get_post(db, post_id) is post
        assert statements == []
        assert flushes == []

        db.flush()
        db.expunge(post)
        statements.clear()
        flushes.clear()
        loaded = references.get_post(db, post_id)
        assert loaded is not None
        assert loaded.deleted_at is not None
        assert loaded.report_hidden_at is not None
        assert "comments" not in loaded.__dict__
        assert len(statements) == 1
        assert statements[0].lstrip().upper().startswith("SELECT")
        assert flushes == []

        db.rollback()
        assert references.get_post(db, post_id).deleted_at is None
        assert references.get_post(db, "absent-interaction-post") is None
    engine.dispose()
