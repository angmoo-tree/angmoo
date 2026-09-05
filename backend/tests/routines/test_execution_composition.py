from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.db import Base
from app.domains.routines import models
from app.domains.routines.policies.activity_state import initial_state
from app.domains.routines.service.execution import claims
from app.domains.social.models.posts import Post
from app.runtime.routines.activity_references import SqlAlchemyActivityReferences
from routines.test_daily_activity_runtime import _prepare, _seed, _utc


@pytest.mark.parametrize("outcome", ["commit", "rollback"])
def test_pending_post_and_beat_completion_share_caller_transaction(tmp_path, outcome):
    engine = create_engine(f"sqlite:///{tmp_path / 'execution-composition.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = _utc(datetime(2026, 8, 9, 0, 30))
    try:
        with Session(engine, expire_on_commit=False) as db:
            world, fixture, _other = _seed(db)
            plan = _prepare(db, fixture, now=now)
            episode = plan.items[0].episode
            assert episode is not None
            claim = claims.claim_activity_beat(
                db,
                episode_id=episode.id,
                scheduled_for=now,
                trigger_kind="scheduled",
                idempotency_key="completion-transaction",
                claim_run_id="completion-run",
                claim_expires_at=now + timedelta(minutes=10),
                now=now,
            )
            beat_id = claim.row.id
            post = Post(
                id="pending-completion-post",
                world_id=world.id,
                author_world_character_id=fixture.world_character.id,
                author_character_id=fixture.character.id,
                author_name=fixture.character.name,
                title="A completed activity",
                body="The publication and narrative state commit together.",
            )
            db.add(post)
            commits = []
            reads = []
            event.listen(db, "after_commit", lambda _session: commits.append(True))

            class ObservedReferences(SqlAlchemyActivityReferences):
                def get_post(self, post_id):
                    result = super().get_post(post_id)
                    assert result is post
                    assert result in db
                    reads.append("post")
                    return result

                def get_world_character(self, world_character_id, *, lock_for_update=False):
                    result = super().get_world_character(
                        world_character_id, lock_for_update=lock_for_update
                    )
                    assert result is fixture.world_character
                    assert result in db
                    assert lock_for_update is False
                    reads.append("world_character")
                    return result

            result = claims.complete_activity_beat(
                db,
                references=ObservedReferences(db),
                beat_id=beat_id,
                claim_run_id="completion-run",
                source_post_id=post.id,
                state_after_snapshot=initial_state(),
                result_snapshot={"post_id": post.id},
                now=now + timedelta(minutes=1),
                commit=False,
            )
            assert result is claim.row
            assert result.status == "succeeded"
            assert reads == ["post", "world_character"]
            assert commits == []
            with Session(engine) as observer:
                assert observer.get(Post, post.id) is None
                assert observer.get(models.ActivityBeat, beat_id).status == "claimed"
            if outcome == "commit":
                db.commit()
                assert commits == [True]
            else:
                db.rollback()
                assert commits == []

        with Session(engine) as observer:
            saved = observer.get(models.ActivityBeat, beat_id)
            saved_episode = observer.get(models.ActivityEpisode, episode.id)
            assert saved is not None
            assert saved_episode is not None
            if outcome == "commit":
                assert observer.get(Post, "pending-completion-post") is not None
                assert saved.status == "succeeded"
                assert saved.source_post_id == "pending-completion-post"
                assert saved_episode.last_successful_beat_id == beat_id
                assert saved_episode.next_sequence_no == 2
            else:
                assert observer.get(Post, "pending-completion-post") is None
                assert saved.status == "claimed"
                assert saved.source_post_id is None
                assert saved_episode.last_successful_beat_id is None
                assert saved_episode.next_sequence_no == 1
    finally:
        engine.dispose()
