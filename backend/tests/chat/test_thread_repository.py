"""Concrete persistence boundaries preserve ownership, ordering and caller UoW."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models as registry
from app.models import Base
from app.domains.chat import models
from app.domains.chat.repository import threads


def test_thread_queries_preserve_owner_deleted_scope_order_and_same_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        owner = registry.User(id="owner", email="owner@example.test", display_name="owner")
        other = registry.User(id="other", email="other@example.test", display_name="other")
        character = registry.Character(
            id="character", owner_id="owner", name="character", handle="character",
            persona_summary="test",
        )
        db.add_all([owner, other, character])
        db.flush()
        values = [
            ("old", "owner", "ambiguous", now, None),
            ("recent", "owner", "quarantined", now + timedelta(seconds=1), None),
            ("latest", "owner", "quarantined", now + timedelta(seconds=2), None),
            ("deleted", "owner", "quarantined", now + timedelta(seconds=3), now),
            ("foreign", "other", "ambiguous", now + timedelta(seconds=4), None),
        ]
        records = [
            models.MessageThread(
                id=identifier, requester_id=requester, character_id=character.id,
                world_scope_status=scope, selected_model="gemini-2.5-flash-lite",
                model_binding_mode="thread_override", created_at=created,
                last_message_at=created, deleted_at=deleted,
            )
            for identifier, requester, scope, created, deleted in values
        ]
        db.add_all(records)
        db.commit()
        commits = []
        event.listen(db, "after_commit", lambda session: commits.append(session))
        rows = threads.list_threads(db, owner.id)
        assert [row.id for row in rows] == ["latest", "recent", "old"]
        assert rows[0] is db.get(models.MessageThread, "latest")
        assert threads.count_active_threads(db, owner.id) == 3
        assert threads.count_ambiguous_threads(db, owner.id) == 3
        assert [row.id for row in threads.find_legacy_thread_candidates(db, owner.id, character.id)] == ["old", "recent"]
        assert threads.get_owned_thread(db, owner.id, "foreign") is None
        assert threads.get_owned_thread(db, owner.id, "deleted") is None
        assert commits == []
        rows[0].selected_model = "gemini-2.5-flash"
        db.flush()
        db.rollback()
        assert db.get(models.MessageThread, "latest").selected_model == "gemini-2.5-flash-lite"
    engine.dispose()
