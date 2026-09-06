import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.social.exceptions import TodaySocialActivityReadError
from app.domains.social.models.posts import Post
from app.runtime.social.today_activity import today_social_activity_reader
from test_p8_l_r_today_sns_activity import NOW, _seed_today_activity, today_session


def test_today_reader_refreshes_canonical_visibility_without_own_commit(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    cached = db.get(Post, "subject-root")
    assert cached.report_hidden_at is None
    with Session(db.bind) as observer:
        post = observer.get(Post, "subject-root")
        post.report_hidden_at = NOW
        observer.commit()
    assert cached.report_hidden_at is None
    statements, commits = [], []
    event.listen(
        db.bind, "before_cursor_execute", lambda *args: statements.append(args[2])
    )
    event.listen(db, "after_commit", lambda session: commits.append(session))
    reader = today_social_activity_reader(db)
    assert reader.repository._db is db
    assert reader.references._db is db
    assert statements == []
    with pytest.raises(
        TodaySocialActivityReadError, match="today_social_day_range_invalid"
    ):
        reader.read(
            owner_id=fixture["owner"].id,
            world_id=fixture["subject"].world_id,
            subject_world_character_id=fixture["subject"].id,
            started_at=NOW,
            complete_through=NOW.replace(hour=0),
        )
    assert statements == []
    result = reader.read(
        owner_id=fixture["owner"].id,
        world_id=fixture["subject"].world_id,
        subject_world_character_id=fixture["subject"].id,
        started_at=NOW.replace(hour=0),
        complete_through=NOW,
    )
    assert cached.report_hidden_at is not None
    assert all(row.source_post_id != "subject-root" for row in result.records)
    assert all(row.root_post_id != "subject-root" for row in result.records)
    assert commits == []
