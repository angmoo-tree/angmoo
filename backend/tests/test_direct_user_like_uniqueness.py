from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.cruds import community


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.Character.__table__.create(engine)
    models.Post.__table__.create(engine)
    models.PostLike.__table__.create(engine)
    return Session(engine)


def test_direct_user_like_is_idempotent_with_database_unique_boundary() -> None:
    db = _session()
    user = models.User(
        id="user-like",
        email="like@example.invalid",
        display_name="like-user",
        display_name_normalized="like-user",
        profile_setup_completed=True,
        feed_content_filter="all",
    )
    post = models.Post(
        id="post-like",
        author_user_id=user.id,
        author_name="like-user",
        title="title",
        body="body",
        post_type="text",
    )
    db.add_all((user, post))
    db.commit()

    first, first_created = community.like_post(
        db,
        post=post,
        user=user,
        character=None,
    )
    second, second_created = community.like_post(
        db,
        post=post,
        user=user,
        character=None,
    )

    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    assert (
        db.scalar(
            select(func.count(models.PostLike.id)).where(
                models.PostLike.post_id == post.id,
                models.PostLike.user_id == user.id,
                models.PostLike.character_id.is_(None),
            )
        )
        == 1
    )
