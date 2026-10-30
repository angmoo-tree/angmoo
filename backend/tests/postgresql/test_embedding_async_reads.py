"""Embedding capture retries fresh DB snapshots without blocking provider work."""
import asyncio
from threading import get_ident
from time import monotonic

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.runtime.memory_embedding_provider import MemoryQueryEmbedder, embedding_material
from postgresql.test_activity_transactions import store


def test_embedding_owned_read_retries_fresh_snapshot_and_returns_connection(store):
    engine, _, _ = store
    factory = sessionmaker(engine)
    embedder = MemoryQueryEmbedder(factory, lambda db: None)
    reads = []
    async def scenario():
        loop_thread = get_ident()
        def capture(db):
            assert get_ident() != loop_thread
            reads.append(db)
            assert db.scalar(text('SHOW transaction_read_only')) == 'on'
            if len(reads) == 1:
                db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'read abort' USING ERRCODE='40001'; END $$"))
            return db.scalar(text('SELECT 42'))
        assert await embedder._read(capture, deadline=monotonic()+3) == 42
        assert engine.pool.checkedout() == 0
    asyncio.run(scenario())
    assert len(reads) == 2 and reads[0] is not reads[1]


def test_embedding_binding_does_not_disguise_postgresql_abort_as_bad_credential(store, monkeypatch):
    engine, _, _ = store
    attempts = []
    def presence(db, scope):
        attempts.append(1)
        if len(attempts) == 1:
            db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'read abort' USING ERRCODE='40001'; END $$"))
        return [object()]
    monkeypatch.setattr('app.runtime.subject_scope.read_scope_presence', presence)
    from types import SimpleNamespace
    material = SimpleNamespace(model='gemini-embedding-2')
    monkeypatch.setattr('app.runtime.memory_embedding_provider.resolve', lambda *args, **kwargs: material)
    embedder = MemoryQueryEmbedder(sessionmaker(engine), lambda db: None)
    scope = SimpleNamespace(owner_id='owner', world_id='world', subject_world_character_id='actor')
    assert asyncio.run(embedder._read(lambda db: embedding_material(db, scope), deadline=monotonic()+3)) is material
    assert attempts == [1, 1] and engine.pool.checkedout() == 0
