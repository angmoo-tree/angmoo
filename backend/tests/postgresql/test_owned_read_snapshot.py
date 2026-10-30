"""Owned search snapshots must not add read/write SSI dependencies."""
import uuid
from time import monotonic
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from postgresql.test_canonical_contracts import engine
from app.core.postgresql_reads import read_transaction


def _pair(engine):
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as db:
        db.execute(text('INSERT INTO g2_test_counter VALUES(:id,0)'),
                   [{'id': first}, {'id': second}])
    return first, second


@contextmanager
def _separate_rows(engine):
    # Separate tables eliminate small-table sequential-scan false positives
    # between the two writers, isolating the third read-only transaction.
    tables = ['g2_read_snapshot_' + uuid.uuid4().hex for _ in range(2)]
    with engine.begin() as db:
        for name in tables:
            db.exec_driver_sql(f'CREATE TABLE {name}(value int NOT NULL)')
            db.exec_driver_sql(f'INSERT INTO {name} VALUES(0)')
    try:
        yield tables
    finally:
        with engine.begin() as db:
            for name in tables:
                db.exec_driver_sql(f'DROP TABLE {name}')


@pytest.mark.parametrize('serializable_reader', [True, False])
def test_owned_read_keeps_snapshot_without_adding_writer_dependencies(engine, monkeypatch, serializable_reader):
    if serializable_reader:
        monkeypatch.setattr('app.core.postgresql_reads.begin_owned_read',
            lambda db: db.exec_driver_sql('SET TRANSACTION READ ONLY'))
    # The two writes can serialize as first, then second. A separately owned
    # search is allowed a consistent MVCC snapshot; it never publishes a write.
    with _separate_rows(engine) as (first, second), engine.connect() as writer:
        transaction = writer.begin()
        writer.exec_driver_sql(f'SELECT value FROM {second}')
        writer.exec_driver_sql(f'UPDATE {first} SET value=1')
        with engine.begin() as other:
            other.exec_driver_sql(f'UPDATE {second} SET value=1')
        write_errors = []
        def read(db):
            before = db.exec_driver_sql(f'SELECT value FROM {first}').scalar_one()
            try:
                transaction.commit()
            except DBAPIError as error:
                write_errors.append(error.orig.sqlstate)
                writer.rollback()
            after = db.exec_driver_sql(f'SELECT value FROM {first}').scalar_one()
            assert (before, after) == (0, 0)
            assert db.scalar(text('SHOW transaction_read_only')) == 'on'
            return before
        assert read_transaction(engine, read, deadline=monotonic()+4) == 0
        assert write_errors == (['40001'] if serializable_reader else [])
        # The next business transaction retains its SERIALIZABLE/write policy.
        with engine.begin() as db:
            assert db.scalar(text('SHOW transaction_isolation')) == 'serializable'
            assert db.scalar(text('SHOW transaction_read_only')) == 'off'
            assert db.exec_driver_sql(f'SELECT value FROM {first}').scalar_one() == (0 if serializable_reader else 1)
    assert engine.pool.checkedout() == 0


def test_owned_snapshot_rejects_business_writes(engine):
    first, _ = _pair(engine)
    def mutate(db):
        db.execute(text('UPDATE g2_test_counter SET value=9 WHERE id=:id'), {'id': first})
    with pytest.raises(DBAPIError) as error:
        read_transaction(engine, mutate, deadline=monotonic()+3)
    assert error.value.orig.sqlstate == '25006'
    with engine.begin() as db:
        assert db.execute(text('SELECT value FROM g2_test_counter WHERE id=:id'), {'id': first}).scalar_one() == 0


def test_cannot_convert_an_existing_business_snapshot_to_owned_read(engine):
    from app.core.postgresql_reads import begin_owned_read
    with engine.connect() as db:
        db.exec_driver_sql('SELECT 1')
        with pytest.raises(DBAPIError) as error:
            begin_owned_read(db)
        assert error.value.orig.sqlstate == '25001'
