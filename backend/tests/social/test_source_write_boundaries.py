from app import models as _registered_models  # Register the current complete ORM metadata before partial DDL.

from types import SimpleNamespace

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.core.unit_of_work import deferred_commits
from app.domains.social.models import posts as models
from app.domains.social.repository import profiles, reactions
from app.domains.social.schemas.community import CommentCreate, PostCreate
from app.domains.social.service import source_posts


def test_source_and_reactions_use_actor_values_and_keep_deferred_transaction():
    engine = create_engine("sqlite://")
    for model in (models.Post, models.PostLike, models.PostReport, models.PostRepost):
        model.__table__.create(engine)
    with Session(engine) as db:
        commits = []
        event.listen(db, "before_commit", lambda *args: commits.append("commit"))
        user = SimpleNamespace(id="source-owner", display_name="Source owner")
        actor = SimpleNamespace(id="source-character", name="Source character")
        with deferred_commits():
            post = source_posts.create_post(db, post_id="source-post", user=user, character=actor, data=PostCreate(title="Source", body="Body"))
            assert post.author_name == "Source character"
            assert post.author_user_id == "source-owner"
            assert post.author_character_id == "source-character"
            like, created = reactions.like_post(db, post=post, user=user, character=None)
            duplicate, duplicate_created = reactions.like_post(db, post=post, user=user, character=None)
            assert created and not duplicate_created and duplicate.id == like.id
            assert reactions.unlike_post(db, post=post, user=user, character=None)
            assert not reactions.unlike_post(db, post=post, user=user, character=None)
            repost, created = reactions.create_repost(db, post=post, user=user, character=None)
            assert created and repost.user_id == user.id
            timeline = source_posts.create_timeline_post(db, post_id="repost-source", user=user, character=None, title="Repost", body="", post_type="repost", repost_of_post_id=post.id)
            assert reactions.get_timeline_repost(db, post=post, user=user, character=None) is timeline
            assert reactions.delete_repost(db, post=post, user=user, character=None)
            assert not reactions.delete_repost(db, post=post, user=user, character=None)
            assert reactions.delete_timeline_reposts(db, post=post, user=user, character=None) == 1
            assert reactions.get_timeline_repost(db, post=post, user=user, character=None) is None
            assert commits == []
        db.rollback()
        assert db.scalar(select(func.count(models.Post.id))) == 0
        assert db.scalar(select(func.count(models.PostLike.id))) == 0
        assert db.scalar(select(func.count(models.PostRepost.id))) == 0
    engine.dispose()


def test_follow_values_dedupe_without_foreign_queries_and_keep_caller_rollback():
    engine = create_engine("sqlite://")
    models.ProfileFollow.__table__.create(engine)
    with Session(engine) as db:
        commits = []
        event.listen(db, "before_commit", lambda *args: commits.append("commit"))
        values = dict(follower_user=SimpleNamespace(id="owner"), follower_character=None, target_user=None, target_character=SimpleNamespace(id="target"))
        with deferred_commits():
            follow, created = profiles.create_follow(db, **values)
            duplicate, duplicate_created = profiles.create_follow(db, **values)
            assert created and not duplicate_created and duplicate is follow
            assert profiles.profile_follow_exists(db, **values)
            assert profiles.delete_follow(db, **values)
            assert not profiles.delete_follow(db, **values)
            assert not profiles.profile_follow_exists(db, **values)
            profiles.create_follow(db, **values)
            assert commits == []
        db.rollback()
        assert db.scalar(select(func.count(models.ProfileFollow.id))) == 0
    engine.dispose()


def test_legacy_comment_retains_its_original_explicit_commit_boundary():
    engine = create_engine("sqlite://")
    models.Comment.__table__.create(engine)
    with Session(engine) as db:
        commits = []
        event.listen(db, "before_commit", lambda *args: commits.append("commit"))
        with deferred_commits():
            comment = source_posts.create_comment(db, models.Post(id="legacy-post"), SimpleNamespace(id="legacy-actor"), CommentCreate(author_character_id="legacy-actor", content="Legacy body"))
        assert commits == ["commit"]
        assert comment.post_id == "legacy-post"
        assert comment.author_character_id == "legacy-actor"
        assert comment.content == "Legacy body"
        db.rollback()
        assert db.scalar(select(func.count(models.Comment.id))) == 1
    engine.dispose()
