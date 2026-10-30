"""Disposable capture must never roll back or repeat an authoritative effect."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.contracts.retrieval_observation import Observation, current
from app.domains.chat.repository import retrieval_diagnostics
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from postgresql.test_activity_transactions import store


def test_diagnostic_abort_does_not_repeat_or_lose_committed_chat(store, monkeypatch):
    engine, _, _ = store
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE canonical_chat_effect (value integer)'))
        connection.execute(text('INSERT INTO canonical_chat_effect VALUES (0)'))
    calls = []
    def fail(db, observation):
        db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'diagnostic abort' USING ERRCODE='40001'; END $$"))
    monkeypatch.setattr(retrieval_diagnostics, 'save', fail)
    token = current.set(Observation(request_id='synthetic-request'))
    try:
        with Session(engine) as db:
            uow = SqlAlchemyResponseWorkflowUnitOfWork(db)
            def effect():
                calls.append(1)
                db.execute(text('UPDATE canonical_chat_effect SET value=value+1'))
                return 'already received AI response'
            assert uow.run_database_unit(effect) == 'already received AI response'
            assert db.is_active and not db.in_transaction()
            assert uow._diagnostic_snapshot is None
    finally:
        current.reset(token)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT value FROM canonical_chat_effect')) == 1
    assert calls == [1]
    assert engine.pool.checkedout() == 0


def test_busy_diagnostic_writer_defers_without_waiting_or_holding_chat_connection(store, monkeypatch):
    engine, _, _ = store
    observed = []
    def capture(db, observation):
        observed.append(db.scalar(text('SHOW transaction_isolation')))
    monkeypatch.setattr(retrieval_diagnostics, 'save', capture)
    observation = Observation(request_id='synthetic-request')
    with engine.begin() as blocker:
        blocker.execute(text('SELECT pg_advisory_xact_lock(1886221416, 1)'))
        assert retrieval_diagnostics.save_postgresql(engine, observation) is False
        assert observed == []
        assert engine.pool.checkedout() == 1
    assert retrieval_diagnostics.save_postgresql(engine, observation) is True
    assert observed == ['read committed']
    assert engine.pool.checkedout() == 0
