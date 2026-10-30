"""Private official Vec1 flat projection with per-operation connection ownership.

Only committed summary vectors are visible. Callers must revalidate every hit
against canonical Memory before using it. This adapter never calls an AI API.
"""
from __future__ import annotations

from app.core import work_observation as observation
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
from threading import Event, Lock
from time import monotonic
from app.runtime.memory.worker_diagnostics import phase, capture_failure, current_worker

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
        from contextvars import ContextVar
        self._effect = ContextVar(f"vector_effect_{id(self)}", default=None)

    @contextmanager
    def effect_connection(self):
        """Load the extension before entering the canonical writer fence."""
        with self._connect() as connection:
            token = self._effect.set(connection)
            try:
                yield
            finally:
                self._effect.reset(token)

    @contextmanager
    def _connect(self, *, cancellation: VectorCancellation | None = None, read_only=False):
        if self._effect.get() is not None:
            yield self._effect.get()
            return
        with phase("db_open"):
            connection = sqlite3.connect(self.database_path.as_uri()+"?mode=ro" if read_only else self.database_path,
                                         uri=read_only, timeout=1.0)
        try:
            with phase("extension_load"):
                connection.enable_load_extension(True)
                try:
                    connection.load_extension(str(self._extension))
                finally:
                    connection.enable_load_extension(False)
            # Derived effects must not hold the canonical writer while waiting.
            connection.execute("PRAGMA busy_timeout=25" if not read_only else "PRAGMA busy_timeout=1000")
            if cancellation is not None:
                cancellation.attach(connection)
            yield connection
        except sqlite3.Error as exc:
            capture_failure(exc)
            error = MemoryVectorProjectionError(
                "memory_vector_cancelled" if cancellation and cancellation.expired()
                else "memory_vector_database_error"
            )
            # Keep only typed SQLite identity, never SQL text or bound values.
            error.sqlite_errorcode = getattr(exc, "sqlite_errorcode", None)
            error.sqlite_errorname = getattr(exc, "sqlite_errorname", None)
            raise error from None
        finally:
            if cancellation is not None:
                cancellation.detach()
            connection.close()

    def open(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection, observation.span("vec1_writer",
                database_id=observation.database_id(self.database_path), writer="vec1_open"):
            connection.execute("PRAGMA journal_mode=WAL")
            observation.emit("sqlite", boundary="begin_started")
            connection.execute("BEGIN IMMEDIATE")
            observation.emit("sqlite", boundary="acquired")
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='projection_profile'").fetchone()
            if not exists:
                connection.execute("CREATE TABLE projection_profile(revision TEXT PRIMARY KEY, generation TEXT NOT NULL)")
                connection.execute("INSERT INTO projection_profile VALUES(?,?)", (SCHEMA_REVISION, self.generation))
                connection.execute("CREATE VIRTUAL TABLE vectors USING vec1(vector, owner_id, world_id, subject_id, profile, occurred_at, counterpart_id, thread_id)")
                connection.execute("INSERT INTO vectors(cmd,arg) VALUES('rebuild',?)", (json.dumps({"index": "flat", "distance": "cos"}),))
                connection.execute("CREATE TABLE documents(rowid INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT UNIQUE NOT NULL, memory_item_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL)")
            if connection.execute("SELECT revision,generation FROM projection_profile").fetchall() != [(SCHEMA_REVISION, self.generation)]:
                raise MemoryVectorProjectionError("memory_vector_profile_mismatch")
            observation.emit("sqlite", boundary="commit_started")
            connection.commit()
            observation.emit("sqlite", boundary="committed")
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
        with self._connect() as connection, observation.span("vec1_writer",
                database_id=observation.database_id(self.database_path), writer="vec1_upsert"):
            observation.emit("sqlite", boundary="begin_started")
            connection.execute("BEGIN IMMEDIATE")
            observation.emit("sqlite", boundary="acquired")
            for document, blob in prepared:
                old = connection.execute("SELECT rowid,version FROM documents WHERE document_id=?", (document.document_id,)).fetchone()
                if old is not None and old[1] > document.version:
                    continue
                connection.execute("INSERT INTO documents(document_id,memory_item_id,version,content_hash) VALUES(?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET memory_item_id=excluded.memory_item_id,version=excluded.version,content_hash=excluded.content_hash", (document.document_id, document.memory_item_id, document.version, document.content_hash))
                rowid = connection.execute("SELECT rowid FROM documents WHERE document_id=?", (document.document_id,)).fetchone()[0]
                connection.execute("DELETE FROM vectors WHERE rowid=?", (rowid,))
                connection.execute("INSERT INTO vectors(rowid,vector,owner_id,world_id,subject_id,profile,occurred_at,counterpart_id,thread_id) VALUES(?,?,?,?,?,?,?,?,?)", (rowid, blob, document.scope.owner_id, document.scope.world_id, document.scope.subject_world_character_id, document.profile, document.occurred_at.timestamp(), document.counterpart_world_character_id, document.thread_id))
            observation.emit("sqlite", boundary="commit_started")
            connection.commit()
            observation.emit("sqlite", boundary="committed")

    def matches(self, document):
        """Exact effect identity, including metadata, without rewriting vectors."""
        with self._connect(read_only=True) as connection:
            row = connection.execute("SELECT d.version,d.content_hash,v.profile,v.owner_id,v.world_id,v.subject_id,v.occurred_at,v.counterpart_id,v.thread_id FROM documents d JOIN vectors v ON v.rowid=d.rowid WHERE d.document_id=?", (document.document_id,)).fetchone()
        return row == (document.version, document.content_hash, document.profile,
            document.scope.owner_id, document.scope.world_id, document.scope.subject_world_character_id,
            document.occurred_at.timestamp(), document.counterpart_world_character_id, document.thread_id)

    def delete(self, document_id: str):
        with self._connect() as connection, observation.span("vec1_writer",
                database_id=observation.database_id(self.database_path), writer="vec1_delete"):
            observation.emit("sqlite", boundary="begin_started")
            connection.execute("BEGIN IMMEDIATE")
            observation.emit("sqlite", boundary="acquired")
            connection.execute("DELETE FROM vectors WHERE rowid IN (SELECT rowid FROM documents WHERE document_id=?)", (document_id,))
            connection.execute("DELETE FROM documents WHERE document_id=?", (document_id,))
            observation.emit("sqlite", boundary="commit_started")
            connection.commit()
            observation.emit("sqlite", boundary="committed")

    def erase_items(self, identifiers):
        identifiers = tuple(identifiers)
        with self._connect() as connection, observation.span("vec1_writer",
                database_id=observation.database_id(self.database_path), writer="vec1_erase_items"):
            observation.emit("sqlite", boundary="begin_started")
            connection.execute("BEGIN IMMEDIATE")
            observation.emit("sqlite", boundary="acquired")
            for identifier in identifiers:
                docs = {f"memory-item:{identifier}"} | {row[0] for row in connection.execute("SELECT document_id FROM documents WHERE memory_item_id=?", (identifier,))}
                connection.execute("DELETE FROM vectors WHERE rowid IN (SELECT rowid FROM documents WHERE memory_item_id=?)", (identifier,))
                connection.execute("DELETE FROM documents WHERE memory_item_id=?", (identifier,))
                if connection.execute("SELECT 1 FROM sqlite_master WHERE name='embedding_attempts_v2'").fetchone():
                    for doc in docs:
                        connection.execute("DELETE FROM embedding_attempts_v2 WHERE document_id=?", (doc,))
            observation.emit("sqlite", boundary="commit_started")
            connection.commit()
            observation.emit("sqlite", boundary="committed")

    def identity(self, document_id):
        with self._connect(read_only=True) as connection:
            return connection.execute("SELECT d.version,d.content_hash,v.profile FROM documents d JOIN vectors v ON v.rowid=d.rowid WHERE d.document_id=?", (document_id,)).fetchone()

    def refresh_version(self, document_id, *, content_hash, version, scope=None,
                        occurred_at=None, counterpart_world_character_id=None, thread_id=None):
        if scope is not None and (occurred_at is None or occurred_at.tzinfo is None):
            raise ValueError("memory_vector_metadata_invalid")
        with self._connect() as connection, observation.span("vec1_writer",
                database_id=observation.database_id(self.database_path), writer="vec1_refresh_version"):
            observation.emit("sqlite", boundary="begin_started")
            connection.execute("BEGIN IMMEDIATE")
            observation.emit("sqlite", boundary="acquired")
            if scope is not None:
                row = connection.execute("SELECT d.rowid,v.vector,v.owner_id,v.world_id,v.subject_id,v.profile,v.occurred_at,v.counterpart_id,v.thread_id FROM documents d JOIN vectors v ON v.rowid=d.rowid WHERE d.document_id=? AND d.content_hash=? AND d.version<=?",
                    (document_id, content_hash, version)).fetchone()
                if row is None:
                    return
                expected = (scope.owner_id, scope.world_id, scope.subject_world_character_id,
                            row[5], occurred_at.timestamp(), counterpart_world_character_id, thread_id)
                if tuple(row[2:]) != expected:
                    # Reuse the exact stored vector. Vec1 metadata changes do
                    # not need another embedding or an in-place UPDATE feature.
                    connection.execute("DELETE FROM vectors WHERE rowid=?", (row[0],))
                    connection.execute("INSERT INTO vectors(rowid,vector,owner_id,world_id,subject_id,profile,occurred_at,counterpart_id,thread_id) VALUES(?,?,?,?,?,?,?,?,?)",
                        (row[0], row[1], *expected))
            connection.execute("UPDATE documents SET version=? WHERE document_id=? AND content_hash=? AND version<=?",
                               (version, document_id, content_hash, version))
            observation.emit("sqlite", boundary="commit_started")
            connection.commit()
            observation.emit("sqlite", boundary="committed")

    def document_upper_bound(self):
        with self._connect(read_only=True) as connection:
            return connection.execute("SELECT max(document_id) FROM documents").fetchone()[0] or ""

    def document_page(self, *, after="", limit=64):
        if not 1 <= limit <= 256:
            raise ValueError("memory_vector_page_limit")
        with self._connect(read_only=True) as connection:
            return tuple(connection.execute("SELECT document_id,memory_item_id FROM documents WHERE document_id>? ORDER BY document_id LIMIT ?", (after, limit)))

    def search(self, query: MemoryVectorQuery, *, cancellation: VectorCancellation):
        started = monotonic()
        with phase("query_validate"):
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
        if query.allowed_thread_ids is not None:
            allowed = query.allowed_thread_ids
            where.append("(thread_id IS NULL" + (f" OR thread_id IN ({','.join('?' for _ in allowed)})" if allowed else "") + ")")
            values.extend(allowed)
        predicate = " AND ".join(where)
        with self._connect(cancellation=cancellation, read_only=True) as connection:
            connection.execute("BEGIN")
            diagnostic = current_worker.get()
            if diagnostic is not None and diagnostic.detailed:
                diagnostic.metadata["metadata_status"] = "budget_skipped"
                with phase("metadata_read"):
                    if cancellation.deadline - monotonic() > 0.05:
                        # One bounded metadata read; never change query acceptance.
                        try:
                            metadata = connection.execute("SELECT revision,generation FROM projection_profile LIMIT 2").fetchall()
                            if len(metadata) == 1:
                                from app.contracts.search_diagnostics import SearchTerminal
                                values_read = dict(observed_schema_revision=metadata[0][0], observed_generation=metadata[0][1],
                                    generation_match=metadata[0][1] == self.generation, metadata_status="observed")
                                SearchTerminal(axis="vector", terminal_state="success", **values_read)
                                diagnostic.metadata.update(values_read)
                            else:
                                diagnostic.metadata["metadata_status"] = "unavailable"
                        except (sqlite3.Error, ValueError, TypeError):
                            diagnostic.metadata["metadata_status"] = "unavailable"
            with phase("eligible_count"):
                count = connection.execute("SELECT count(*) FROM vectors WHERE " + predicate, values).fetchone()[0]
                if diagnostic is not None:
                    diagnostic.metadata["eligible_vector_count"] = count
            # Vec1's empty flat model has dimension zero until its first insert.
            rows = []
            if count:
                with phase("nn_query"):
                    rows = connection.execute(
                        "SELECT rowid,distance FROM vectors(?,?) WHERE " + predicate,
                        [blob, query.limit, *values],
                    ).fetchall()
            hits = []
            with phase("mapping_read"):
                for rowid, distance in rows:
                    record = connection.execute("SELECT document_id,memory_item_id,version,content_hash FROM documents WHERE rowid=?", (rowid,)).fetchone()
                    if record is None:
                        raise MemoryVectorProjectionError("memory_vector_mapping_missing")
                    hits.append(MemoryVectorHit(*record, distance))
            if cancellation.expired():
                raise MemoryVectorProjectionError("memory_vector_cancelled")
        return MemoryVectorSearchResult(tuple(hits), count, self.generation, (monotonic()-started)*1000)
