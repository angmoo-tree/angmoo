"""Vector proof reads own one stable snapshot and release it on every exit."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from postgresql.test_canonical_contracts import engine, no_sqlite
from app.runtime.memory.vector_preparation import credential_proof
from app.runtime.memory.vector_proof import snapshot


@pytest.mark.parametrize('path', ['item', 'credential'])
@pytest.mark.parametrize('exit_kind', ['return', 'exception', 'write'])
def test_vector_proof_snapshot_and_cleanup(engine, path, exit_kind):
    key = uuid4().hex
    with engine.begin() as db:
        db.execute(text('INSERT INTO g2_test_counter VALUES(:key,0)'), {'key': key})

    class Reader(Session):
        pass

    notices, connections, observed = [], set(), []
    def notice(value):
        notices.append(value.sqlstate)
    def checkout(connection, record, proxy):
        if connection not in connections:
            connections.add(connection)
            connection.add_notice_handler(notice)
    def first_read(state):
        if observed or not state.is_select:
            return
        observed.append(True)
        db = state.session
        assert db.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
        assert db.scalar(text('SHOW transaction_read_only')) == 'on'
        before = db.scalar(text('SELECT value FROM g2_test_counter WHERE id=:key'), {'key': key})
        # Other work can commit while this reader keeps its original snapshot.
        with engine.begin() as other:
            other.execute(text('UPDATE g2_test_counter SET value=1 WHERE id=:key'), {'key': key})
        assert db.scalar(text('SELECT value FROM g2_test_counter WHERE id=:key'), {'key': key}) == before == 0
        if exit_kind == 'exception':
            raise ValueError('proof_read_interrupted')
        if exit_kind == 'write':
            db.execute(text('UPDATE g2_test_counter SET value=2 WHERE id=:key'), {'key': key})

    event.listen(engine, 'checkout', checkout)
    event.listen(Reader, 'do_orm_execute', first_read)
    try:
        projection = SimpleNamespace(_factory=sessionmaker(engine, class_=Reader))
        def invoke():
            if path == 'item':
                return snapshot(projection, 'absent-' + key, None)[0]
            return credential_proof(projection, 'absent-' + key)
        if exit_kind == 'exception':
            with pytest.raises(ValueError, match='proof_read_interrupted'):
                invoke()
        elif exit_kind == 'write':
            with pytest.raises(DBAPIError) as error:
                invoke()
            assert error.value.orig.sqlstate == '25006'
        else:
            assert invoke() is None
        assert observed == [True] and '25001' not in notices
        assert engine.pool.checkedout() == 0
        with engine.begin() as db:
            assert db.scalar(text('SHOW transaction_isolation')) == 'serializable'
            assert db.scalar(text('SHOW transaction_read_only')) == 'off'
            assert db.scalar(text('SELECT value FROM g2_test_counter WHERE id=:key'), {'key': key}) == 1
    finally:
        event.remove(Reader, 'do_orm_execute', first_read)
        event.remove(engine, 'checkout', checkout)
        for connection in connections:
            if not connection.closed:
                connection.remove_notice_handler(notice)
