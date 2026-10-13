"""Durable index double for worker lifecycle tests; does not simulate NN quality.

The separate test_sqlite_vec1 suite still requires the real verified extension.
These tests exercise canonical fences, durable attempts and explicit enrollment.
"""
from contextlib import contextmanager
import json
import sqlite3
import pytest
from app.runtime.memory.sqlite_vec1 import vector_blob

A = [1.0] + [0.0] * 767


class DurableIndex:
    def __init__(self, path):
        self.path = path
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS test_documents (id TEXT PRIMARY KEY, item TEXT, version INTEGER, digest TEXT, profile TEXT, scope TEXT)")
            db.commit()
    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        try:
            yield connection
        finally:
            connection.close()
    def identity(self, identifier):
        with self._connect() as db:
            return db.execute("SELECT version,digest,profile FROM test_documents WHERE id=?", (identifier,)).fetchone()
    def upsert(self, documents):
        with self._connect() as db:
            for doc in documents:
                vector_blob(doc.vector)
                db.execute("INSERT OR REPLACE INTO test_documents VALUES (?,?,?,?,?,?)",
                    (doc.document_id, doc.memory_item_id, doc.version, doc.content_hash, doc.profile,
                        json.dumps([doc.scope.owner_id, doc.scope.world_id, doc.scope.subject_world_character_id])))
            db.commit()
    def refresh_version(self, identifier, *, content_hash, version, **kwargs):
        with self._connect() as db:
            db.execute("UPDATE test_documents SET version=? WHERE id=? AND digest=?", (version, identifier, content_hash))
            db.commit()
    def delete(self, identifier):
        with self._connect() as db:
            db.execute("DELETE FROM test_documents WHERE id=?", (identifier,)); db.commit()
    def document_page(self, *, after="", limit=64):
        with self._connect() as db:
            return db.execute("SELECT id,item FROM test_documents WHERE id>? ORDER BY id LIMIT ?", (after, limit)).fetchall()


@pytest.fixture
def index(tmp_path):
    return DurableIndex(tmp_path / "test-worker-projection.sqlite3")
