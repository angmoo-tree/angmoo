"""Real connections remain bounded and close before admissions are returned."""
import os
import time
from contextlib import ExitStack

import psycopg
import pytest

from app.core.postgresql_connections import serving_connection, PostgresDirectConnectionBusy


@pytest.fixture
def dsn():
    value=os.environ.get('ANGMOO_EXPERIMENT_DATABASE_URL')
    if not value:pytest.skip('explicit experiment PostgreSQL required')
    return value.replace('postgresql+psycopg://','postgresql://',1)


def test_two_direct_connections_then_bounded_rejection_and_reuse(dsn):
    with ExitStack() as stack:
        first=stack.enter_context(serving_connection(dsn))
        second=stack.enter_context(serving_connection(dsn))
        assert first.execute('SELECT 1').fetchone()==(1,)
        assert second.execute('SELECT 2').fetchone()==(2,)
        start=time.monotonic()
        with pytest.raises(PostgresDirectConnectionBusy):
            with serving_connection(dsn,admission_timeout=.05):pytest.fail('third connection admitted')
        assert .04<=time.monotonic()-start<1
    assert first.closed and second.closed
    with serving_connection(dsn) as third:
        assert third.execute('SELECT 3').fetchone()==(3,)
    assert third.closed


def test_failed_transaction_rolls_back_closes_and_returns_admission(dsn):
    for _ in range(3):
        with pytest.raises(psycopg.errors.DivisionByZero):
            with serving_connection(dsn) as connection:connection.execute('SELECT 1/0')
        assert connection.closed
    with serving_connection(dsn) as connection:
        assert connection.execute('SELECT 1').fetchone()==(1,)
