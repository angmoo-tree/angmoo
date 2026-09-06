from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models as registered_models
from app.models import Base
from app.domains.social.models import posts as models
from app.domains.social.repository import resident_context as queries
from routine_posts.test_runtime import _seed


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'resident-context.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _post(post_id, character_id, *, parent_id=None, hidden=False, deleted=False):
    return models.Post(
        id=post_id, author_character_id=character_id, author_name="Mira",
        title=post_id, body="A reply", reply_to_post_id=parent_id,
        report_hidden_at=datetime.now(UTC) if hidden else None,
        deleted_at=datetime.now(UTC) if deleted else None,
    )


def test_resident_reaction_queries_see_caller_pending_rows_and_preserve_rollback(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        db.add(_post("root", character_id))
        db.commit()
        assert not queries._has_character_like(db, post_id="root", character_id=character_id)
        like = models.PostLike(post_id="root", user_id=fixture.user.id, character_id=character_id)
        repost = models.PostRepost(post_id="root", character_id=character_id)
        follow = models.ProfileFollow(follower_character_id=character_id, target_character_id=character_id)
        db.add_all([like, repost, follow])
        assert queries._has_character_like(db, post_id="root", character_id=character_id)
        assert queries._has_character_repost(db, post_id="root", character_id=character_id)
        assert queries.find_follow_id(db, follower_character_id=character_id, target_character_id=character_id) == follow.id
        assert not queries._has_character_like(db, post_id="root", character_id="different-character")
        assert queries.find_follow_id(db, follower_character_id="different-character", target_character_id=character_id) is None
        with Session(engine) as observer:
            assert not queries._has_character_like(observer, post_id="root", character_id=character_id)
            assert not queries._has_character_repost(observer, post_id="root", character_id=character_id)
            assert queries.find_follow_id(observer, follower_character_id=character_id, target_character_id=character_id) is None
        db.rollback()
        assert not queries._has_character_like(db, post_id="root", character_id=character_id)
        assert not queries._has_character_repost(db, post_id="root", character_id=character_id)
        assert queries.find_follow_id(db, follower_character_id=character_id, target_character_id=character_id) is None
    engine.dispose()


def test_resident_thread_queries_keep_visible_ancestry_direct_reply_and_no_commit(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        root = _post("root", character_id)
        db.add(root)
        db.commit()
        visible = _post("visible", character_id, parent_id=root.id)
        hidden = _post("hidden", character_id, parent_id=root.id, hidden=True)
        deleted = _post("deleted", character_id, parent_id=root.id, deleted=True)
        db.add_all([visible, hidden, deleted])
        db.flush()
        nested = _post("nested", character_id, parent_id=visible.id)
        unreachable = _post("hidden-child", character_id, parent_id=hidden.id)
        db.add_all([nested, unreachable])
        assert queries._thread_reply_post_ids_for_action_gate(db, root.id) == ["visible", "nested"]
        assert queries._has_character_replied_to_thread(db, root_post_id=root.id, character_id=character_id)
        assert not queries._has_character_replied_to_thread(db, root_post_id=root.id, character_id="other")
        assert queries._is_direct_reply_to_character_post_for_action_gate(db, post_id=visible.id, character_id=character_id)
        assert not queries._is_direct_reply_to_character_post_for_action_gate(db, post_id=hidden.id, character_id=character_id)
        assert not queries._is_direct_reply_to_character_post_for_action_gate(db, post_id=root.id, character_id=character_id)
        with Session(engine) as observer:
            assert queries._thread_reply_post_ids_for_action_gate(observer, root.id) == []
        db.rollback()
        assert queries._thread_reply_post_ids_for_action_gate(db, root.id) == []
    engine.dispose()
