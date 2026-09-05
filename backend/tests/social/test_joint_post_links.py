from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.domains.social.models.posts import Post
from app.domains.social.service.joint_posts import set_joint_activity_id, set_opening_post_id


def test_joint_links_keep_assignment_stages_and_caller_rollback():
    engine = create_engine("sqlite://")
    Post.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        post = Post(id="joint-source-post", body="synthetic", title="Synthetic", author_name="Synthetic")
        db.add(post)
        db.commit()
        events = []
        event.listen(db, "before_flush", lambda *args: events.append("flush"))
        event.listen(db, "before_commit", lambda *args: events.append("commit"))
        set_joint_activity_id(post, joint_activity_id="joint-1")
        assert post.joint_activity_id == "joint-1"
        assert post.opening_post_id is None
        assert events == []
        set_opening_post_id(post, opening_post_id="opening-1")
        assert post.opening_post_id == "opening-1"
        assert events == []
        assert post in db.dirty
        db.rollback()
        assert post.joint_activity_id is None
        assert post.opening_post_id is None
        assert events == []
    engine.dispose()
