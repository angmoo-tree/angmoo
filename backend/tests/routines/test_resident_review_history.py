from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.routines.models import AgentActivityLog
from app.domains.routines.repository import resident_context as queries
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_relationship_review_time_observes_pending_log_without_committing(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        now = datetime.now(UTC).replace(tzinfo=None)
        assert queries.latest_relationship_review_at(db, character_id=actor) is None
        db.add_all([
            AgentActivityLog(user_id=fixture.user.id, character_id=actor,
                             action_type="relationship_reviewed", created_at=now - timedelta(days=1)),
            AgentActivityLog(user_id=fixture.user.id, character_id=actor,
                             action_type="relationship_reviewed", created_at=now),
            AgentActivityLog(user_id=fixture.user.id, character_id=actor,
                             action_type="observed", created_at=now + timedelta(days=1)),
        ])
        assert queries.latest_relationship_review_at(db, character_id=actor) == now
        assert queries.latest_relationship_review_at(db, character_id="absent-character") is None
        with Session(engine) as observer:
            assert queries.latest_relationship_review_at(observer, character_id=actor) is None
        db.rollback()
        assert queries.latest_relationship_review_at(db, character_id=actor) is None
    engine.dispose()
