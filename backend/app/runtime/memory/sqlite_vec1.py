"""Private official Vec1 flat projection with per-operation connection ownership.

Only committed summary vectors are visible. Callers must revalidate every hit
against canonical Memory before using it. This adapter never calls an AI API.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
from threading import Event, Lock
from time import monotonic

from app.domains.memory.contracts.vector_projection import (
    MemoryVectorDocument, MemoryVectorHit, MemoryVectorQuery, MemoryVectorSearchResult,
)


DIMENSIONS = 768
SCHEMA_REVISION = "memory-vec1-flat.v1"


class MemoryVectorProjectionError(RuntimeError):
    pass


class VectorCancellation:
    """Interrupt SQLite VM work; process ownership bounds Vec1's native loop."""
    def __init__(self, deadline: float):
        self.deadline = deadline
        self._cancelled = Event()
        self._lock = Lock()
        self._connection: sqlite3.Connection | None = None

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            if self._connection is not None:
                self._connection.interrupt()

    def expired(self):
        return self._cancelled.is_set() or monotonic() >= self.deadline

    def attach(self, connection):
        with self._lock:
            if self.expired():
                raise MemoryVectorProjectionError("memory_vector_cancelled")
            self._connection = connection
        connection.set_progress_handler(lambda: int(self.expired()), 1000)

    def detach(self):
        with self._lock:
            self._connection = None


def vector_blob(vector) -> bytes:
    if len(vector) != DIMENSIONS or any(
        isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
        for x in vector
    ):
        raise ValueError("memory_vector_invalid")
    try:
        blob = struct.pack(f"={DIMENSIONS}f", *vector)
    except (OverflowError, struct.error):
        raise ValueError("memory_vector_invalid") from None
    values = struct.unpack(f"={DIMENSIONS}f", blob)
    if any(not math.isfinite(x) for x in values) or not any(values):
        raise ValueError("memory_vector_invalid")
    return blob


class SqliteMemoryVectorIndex:
    def __init__(self, database_path: Path, *, extension_path: Path,
                 extension_sha256: str, generation: str = "v1"):
        self.database_path = database_path.resolve()
        self._extension = extension_path.resolve(strict=True)
        if (not self._extension.is_file() or len(extension_sha256) != 64
                or hashlib.sha256(self._extension.read_bytes()).hexdigest() != extension_sha256.lower()):
            raise MemoryVectorProjectionError("memory_vector_extension_integrity")
        self.generation = generation

    @contextmanager
    def _connect(self, *, cancellation: VectorCancellation | None = None, read_only=False):
        connection = sqlite3.connect(self.database_path.as_uri()+"?mode=ro" if read_only else self.database_path,
                                     uri=read_only, timeout=1.0)
        try:
            connection.enable_load_extension(True)
            try:
                connection.load_extension(str(self._extension))
            finally:
                connection.enable_load_extension(False)
            connection.execute("PRAGMA busy_timeout=1000")
            if cancellation is not None:
                cancellation.attach(connection)
            yield connection
        except sqlite3.Error:
            raise MemoryVectorProjectionError(
                "memory_vector_cancelled" if cancellation and cancellation.expired()
                else "memory_vector_database_error"
            ) from None
        finally:
            if cancellation is not None:
                cancellation.detach()
            connection.close()

    def open(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='projection_profile'").fetchone()
            if not exists:
                connection.execute("CREATE TABLE projection_profile(revision TEXT PRIMARY KEY, generation TEXT NOT NULL)")
                connection.execute("INSERT INTO projection_profile VALUES(?,?)", (SCHEMA_REVISION, self.generation))
                connection.execute("CREATE VIRTUAL TABLE vectors USING vec1(vector, owner_id, world_id, subject_id, profile, occurred_at, counterpart_id, thread_id)")
                connection.execute("INSERT INTO vectors(cmd,arg) VALUES('rebuild',?)", (json.dumps({"index": "flat", "distance": "cos"}),))
                connection.execute("CREATE TABLE documents(rowid INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT UNIQUE NOT NULL, memory_item_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL)")
            if connection.execute("SELECT revision,generation FROM projection_profile").fetchall() != [(SCHEMA_REVISION, self.generation)]:
                raise MemoryVectorProjectionError("memory_vector_profile_mismatch")
            connection.commit()
            # Inspect the extension's own catalog, not just our bookkeeping.
            connection.execute("SELECT count(*) FROM vectors").fetchone()
            model = connection.execute("SELECT model FROM vec1cat WHERE name='vectors'").fetchone()
            if model is None or json.loads(model[0]) != {"index": "flat", "distance": "cos"}:
                raise MemoryVectorProjectionError("memory_vector_index_mode_mismatch")
            return connection.execute("SELECT vec1_info()").fetchone()[0]

    def upsert(self, documents: tuple[MemoryVectorDocument, ...]):
        prepared = [(d, vector_blob(d.vector)) for d in documents]
        if any(d.version < 1 or not d.profile or len(d.content_hash) != 64
               or not d.document_id or d.occurred_at.tzinfo is None for d, _ in prepared):
            raise ValueError("memory_vector_document_invalid")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for document, blob in prepared:
                old = connection.execute("SELECT rowid,version FROM documents WHERE document_id=?", (document.document_id,)).fetchone()
                if old is not None and old[1] > document.version:
                    continue
                connection.execute("INSERT INTO documents(document_id,memory_item_id,version,content_hash) VALUES(?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET memory_item_id=excluded.memory_item_id,version=excluded.version,content_hash=excluded.content_hash", (document.document_id, document.memory_item_id, document.version, document.content_hash))
                rowid = connection.execute("SELECT rowid FROM documents WHERE document_id=?", (document.document_id,)).fetchone()[0]
                connection.execute("DELETE FROM vectors WHERE rowid=?", (rowid,))
                connection.execute("INSERT INTO vectors(rowid,vector,owner_id,world_id,subject_id,profile,occurred_at,counterpart_id,thread_id) VALUES(?,?,?,?,?,?,?,?,?)", (rowid, blob, document.scope.owner_id, document.scope.world_id, document.scope.subject_world_character_id, document.profile, document.occurred_at.timestamp(), document.counterpart_world_character_id, document.thread_id))
            connection.commit()

    def delete(self, document_id: str):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM vectors WHERE rowid IN (SELECT rowid FROM documents WHERE document_id=?)", (document_id,))
            connection.execute("DELETE FROM documents WHERE document_id=?", (document_id,))
            connection.commit()

    def identity(self, document_id):
        with self._connect(read_only=True) as connection:
            return connection.execute("SELECT d.version,d.content_hash,v.profile FROM documents d JOIN vectors v ON v.rowid=d.rowid WHERE d.document_id=?", (document_id,)).fetchone()

    def refresh_version(self, document_id, *, content_hash, version):
        with self._connect() as connection:
            connection.execute("UPDATE documents SET version=? WHERE document_id=? AND content_hash=? AND version<=?",
                               (version, document_id, content_hash, version))
            connection.commit()

    def document_page(self, *, after="", limit=64):
        if not 1 <= limit <= 256:
            raise ValueError("memory_vector_page_limit")
        with self._connect(read_only=True) as connection:
            return tuple(connection.execute("SELECT document_id,memory_item_id FROM documents WHERE document_id>? ORDER BY document_id LIMIT ?", (after, limit)))

    def search(self, query: MemoryVectorQuery, *, cancellation: VectorCancellation):
        started = monotonic()
        blob = vector_blob(query.vector)
        where = ["owner_id=?", "world_id=?", "subject_id=?", "profile=?"]
        values = [query.scope.owner_id, query.scope.world_id, query.scope.subject_world_character_id, query.profile]
        for clause, value in (
            ("occurred_at>=?", None if query.occurred_from is None else query.occurred_from.timestamp()),
            ("occurred_at<?", None if query.occurred_to is None else query.occurred_to.timestamp()),
            ("counterpart_id=?", query.counterpart_world_character_id), ("thread_id=?", query.thread_id),
        ):
            if value is not None:
                where.append(clause)
                values.append(value)
        predicate = " AND ".join(where)
        with self._connect(cancellation=cancellation, read_only=True) as connection:
            connection.execute("BEGIN")
            count = connection.execute("SELECT count(*) FROM vectors WHERE " + predicate, values).fetchone()[0]
            # Vec1's empty flat model has dimension zero until its first insert.
            rows = [] if count == 0 else connection.execute(
                "SELECT rowid,distance FROM vectors(?,?) WHERE " + predicate,
                [blob, query.limit, *values],
            ).fetchall()
            hits = []
            for rowid, distance in rows:
                record = connection.execute("SELECT document_id,memory_item_id,version,content_hash FROM documents WHERE rowid=?", (rowid,)).fetchone()
                if record is None:
                    raise MemoryVectorProjectionError("memory_vector_mapping_missing")
                hits.append(MemoryVectorHit(*record, distance))
            if cancellation.expired():
                raise MemoryVectorProjectionError("memory_vector_cancelled")
        return MemoryVectorSearchResult(tuple(hits), count, self.generation, (monotonic()-started)*1000)
