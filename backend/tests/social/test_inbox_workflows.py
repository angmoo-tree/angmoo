from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models  # Register complete metadata before partial fixture DDL.
from app.core.unit_of_work import deferred_commits
from app.domains.social.exceptions import NotificationNotFoundError
from app.domains.social.service import inbox
from app.runtime.social.inbox import inbox_service, user_inbox_reads


@pytest.fixture
def inbox_session():
    engine = create_engine("sqlite://")
    for model in (models.User, models.Character, models.Notification):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = models.User(id="owner", email="owner@example.invalid", display_name="Owner", display_name_normalized="owner")
        other = models.User(id="other", email="other@example.invalid", display_name="Other", display_name_normalized="other")
        owned = models.Character(id="owned", owner_id=owner.id, name="Owned", handle="owned", persona_summary="synthetic")
        deleted = models.Character(id="deleted", owner_id=owner.id, name="Deleted", handle="deleted", persona_summary="synthetic", deleted_at=datetime(2026, 9, 5, tzinfo=UTC))
        foreign = models.Character(id="foreign", owner_id=other.id, name="Foreign", handle="foreign", persona_summary="synthetic")
        rows = [
            models.Notification(id=1, recipient_user_id=owner.id, notification_type="reply"),
            models.Notification(id=2, recipient_character_id=owned.id, notification_type="mention"),
            models.Notification(id=3, recipient_character_id=deleted.id, notification_type="follow"),
            models.Notification(id=4, recipient_character_id=foreign.id, notification_type="reply"),
            models.Notification(id=5, recipient_user_id=other.id, notification_type="reply"),
        ]
        db.add_all([owner, other, owned, deleted, foreign, *rows])
        db.commit()
        yield db, owner, other, owned, rows
    engine.dispose()


def test_user_inbox_keeps_single_owner_subquery_and_cursor_scope(inbox_session):
    db, owner, other, owned, rows = inbox_session
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    page, cursor = user_inbox_reads.list_notifications(db, user=owner, limit=1)
    assert page == [rows[1]] and cursor == "2"
    assert len(statements) == 1
    assert "SELECT characters.id" in statements[0]
    statements.clear()
    second, next_cursor = user_inbox_reads.list_notifications(db, user=owner, limit=1, cursor=cursor)
    assert second == [rows[0]] and next_cursor is None
    assert len(statements) == 1
    malformed, malformed_cursor = user_inbox_reads.list_notifications(db, user=owner, limit=100, cursor="invalid")
    assert malformed == [rows[1], rows[0]] and malformed_cursor is None
    assert user_inbox_reads.get_notification_for_user(db, user=owner, notification_id=3) is None
    assert user_inbox_reads.get_notification_for_user(db, user=owner, notification_id=4) is None
    assert user_inbox_reads.get_notification_for_user(db, user=owner, notification_id=5) is None
    result = inbox_service.list_notifications(db, owner, limit=1)
    assert [item.id for item in result.items] == [2] and result.next_cursor == "2"


def test_read_workflow_keeps_missing_guard_and_original_explicit_commit(inbox_session):
    db, owner, other, owned, rows = inbox_session
    commits = []
    event.listen(db, "before_commit", lambda *args: commits.append("commit"))
    with pytest.raises(NotificationNotFoundError):
        inbox_service.mark_notification_read(db, owner, rows[3].id)
    assert rows[3].read_at is None and commits == []
    owner.display_name = "Pending owner change"
    with deferred_commits():
        result = inbox_service.mark_notification_read(db, owner, rows[1].id)
    assert result.id == rows[1].id and result.read_at is not None
    assert commits == ["commit"]
    assert db.get(models.Notification, rows[1].id) is rows[1]
    db.rollback()
    db.expire_all()
    assert rows[1].read_at is not None
    assert owner.display_name == "Pending owner change"


def test_character_inbox_keeps_explicit_user_or_character_scope(inbox_session):
    db, owner, other, owned, rows = inbox_session
    result = inbox.list_notifications_for_character(db, user_id=owner.id, character_id=owned.id)
    assert [item.id for item in result.items] == [2, 1]
    with pytest.raises(NotificationNotFoundError):
        inbox.mark_character_notification_read(db, user_id=owner.id, character_id=owned.id, notification_id=4)
    assert rows[3].read_at is None
    result = inbox.mark_character_notification_read(db, user_id=owner.id, character_id=owned.id, notification_id=1)
    assert result.id == 1 and result.read_at is not None
