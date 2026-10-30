"""Actual PG bulk notification updates, idempotency and recipient fencing."""
from uuid import uuid4
import pytest
from sqlalchemy import event,select
from postgresql.test_canonical_contracts import engine,no_sqlite
from app.database import create_session_factory
from app.core.database_transactions import database_write
from app.domains.social.contracts.world_notifications import WorldNotificationError
from social.test_world_notifications_bulk import seed_many
from social.test_world_user_notifications import service,WORLD,USER,ME
from app.domains.social.models.posts import Notification


@pytest.mark.parametrize('count',[0,1,41])
def test_bulk_read_count_and_replay_on_postgresql(engine,count):
    factory=create_session_factory(engine)
    seed_many(factory,count,prefix='pg-notifications-'+uuid4().hex)
    with factory() as session:
        before=service(session).count(world_id=WORLD,user_id=USER).unread_count
        previous={row.id:row.read_at for row in session.scalars(select(Notification).where(Notification.read_at.is_not(None)))}
    statements=[]
    def record(conn,cursor,statement,*args):statements.append(statement)
    event.listen(engine,'before_cursor_execute',record)
    try:
        with factory() as session:
            value=database_write(session,lambda:service(session).mark_all_read(world_id=WORLD,user_id=USER,recipient_world_character_id=ME))
        assert value.marked_count==before and value.unread_count==0
        with factory() as session:
            replay=database_write(session,lambda:service(session).mark_all_read(world_id=WORLD,user_id=USER,recipient_world_character_id=ME))
            assert replay.marked_count==0 and replay.unread_count==0 and replay.read_at is None
            assert all(session.get(Notification,key).read_at==at for key,at in previous.items())
    finally:event.remove(engine,'before_cursor_execute',record)
    assert not any('changes()' in statement for statement in statements)


def test_wrong_recipient_cannot_mark_notifications(engine):
    factory=create_session_factory(engine)
    seed_many(factory,1,prefix='pg-recipient-'+uuid4().hex)
    with factory() as session:before=service(session).count(world_id=WORLD,user_id=USER).unread_count
    with factory() as session,pytest.raises(WorldNotificationError,match='notification_scope_changed'):
        database_write(session,lambda:service(session).mark_all_read(world_id=WORLD,user_id=USER,recipient_world_character_id='unrelated-recipient'))
    with factory() as session:assert service(session).count(world_id=WORLD,user_id=USER).unread_count==before
