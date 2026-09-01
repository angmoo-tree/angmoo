"""Private, rebuildable FTS5 projection for canonical Memory recall.

This database is deliberately separate from the P5 public-feed search index.
It is a disposable projection: canonical SQLite remains the source of truth,
and every hit must be revalidated before it can become Character evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
import unicodedata

from app.core.search_text import normalize_search_text
from app.domains.memory.public import (
    MEMORY_RECALL_GENERATION,
    MEMORY_RECALL_SCHEMA_VERSION,
    MemoryRecallCandidate,
    MemoryRecallDoctor,
    MemoryRecallDocument,
    MemoryRecallSearchQuery,
    MemorySourceTypeV1,
    RecallDocumentKind,
)
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort


_GENERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_WORD_PATTERN = re.compile(r"[\w]+", re.UNICODE)
_TOKENIZER_STRATEGY = "unicode61 + CJK bigram terms + normalized substring fallback"


class MemoryRecallIndexError(RuntimeError):
    pass


class MemoryRecallIndexSchemaError(MemoryRecallIndexError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryRecallIndexSettings:
    generation: str = MEMORY_RECALL_GENERATION
    busy_timeout_ms: int = 5_000
    synchronous: str = "FULL"

    def __post_init__(self) -> None:
        if not _GENERATION_PATTERN.fullmatch(self.generation):
            raise ValueError("invalid Memory recall FTS5 generation")
        if self.busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        if self.synchronous not in {"NORMAL", "FULL"}:
            raise ValueError("synchronous must be NORMAL or FULL")


class SqliteMemoryRecallIndex:
    """Own the non-canonical P8 recall projection and one rollback image."""

    def __init__(
        self,
        data_paths: RuntimeDataPathPort,
        *,
        settings: MemoryRecallIndexSettings | None = None,
    ) -> None:
        self.settings = settings or MemoryRecallIndexSettings()
        paths = data_paths.resolve()
        directory = (
            paths.search
            / "memory-recall"
            / "generations"
            / self.settings.generation
        )
        self.database_path = directory / "angmoo-memory-recall.sqlite3"
        self.staging_path = directory / "angmoo-memory-recall.staging.sqlite3"
        self.rollback_path = directory / "angmoo-memory-recall.rollback.sqlite3"
        self._opened = False
        self._lock = RLock()

    def open(self) -> MemoryRecallDoctor:
        with self._lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.database_path.exists():
                self._build_database(self.database_path, ())
            else:
                with self._connect(self.database_path) as connection:
                    self._validate_schema(connection)
            self._opened = True
            return self.doctor()

    def close(self) -> None:
        self._opened = False

    def rebuild(
        self,
        documents: Iterable[MemoryRecallDocument],
    ) -> MemoryRecallDoctor:
        """Build in staging, verify, promote atomically, and retain rollback."""

        prepared = _prepare_unique_documents(documents)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            _remove_database_family(self.staging_path)
            self._build_database(self.staging_path, prepared.values())
            staging_doctor = self._doctor_path(self.staging_path)
            if not staging_doctor.healthy:
                _remove_database_family(self.staging_path)
                raise MemoryRecallIndexError("Memory recall staging verification failed")
            self._checkpoint_path(self.staging_path)

            had_current = self.database_path.exists()
            try:
                if had_current:
                    self._checkpoint_path(self.database_path)
                    _remove_database_family(self.rollback_path)
                    os.replace(self.database_path, self.rollback_path)
                os.replace(self.staging_path, self.database_path)
                self._opened = True
                doctor = self._doctor_path(self.database_path)
                if not doctor.healthy:
                    raise MemoryRecallIndexError("Memory recall promotion verification failed")
                return doctor
            except Exception:
                _remove_database_family(self.staging_path)
                if had_current and self.rollback_path.exists():
                    _remove_database_family(self.database_path)
                    os.replace(self.rollback_path, self.database_path)
                self._opened = self.database_path.exists()
                raise

    def rollback(self) -> MemoryRecallDoctor:
        self._require_open()
        with self._lock:
            if not self.rollback_path.exists():
                raise MemoryRecallIndexError("Memory recall rollback image is unavailable")
            self._checkpoint_path(self.database_path)
            swap_path = self.database_path.with_name(
                "angmoo-memory-recall.swap.sqlite3"
            )
            _remove_database_family(swap_path)
            os.replace(self.database_path, swap_path)
            try:
                os.replace(self.rollback_path, self.database_path)
                os.replace(swap_path, self.rollback_path)
                doctor = self._doctor_path(self.database_path)
                if not doctor.healthy:
                    raise MemoryRecallIndexError("Memory recall rollback verification failed")
                return doctor
            except Exception:
                if swap_path.exists() and not self.database_path.exists():
                    os.replace(swap_path, self.database_path)
                raise

    def replace_memory_item(
        self,
        *,
        memory_item_id: str,
        documents: Iterable[MemoryRecallDocument],
        tombstoned_at: datetime | None = None,
    ) -> None:
        self._require_open()
        item_id = _required_identifier(memory_item_id, "memory_item_id")
        prepared = _prepare_unique_documents(documents)
        if any(value.memory_item_id != item_id for value in prepared.values()):
            raise ValueError("Memory recall replacement item mismatch")
        tombstone_text = _utc_text(tombstoned_at or datetime.now(UTC))
        with self._write_transaction() as connection:
            self._tombstone_item(connection, item_id, tombstone_text)
            for document_id in sorted(prepared):
                self._upsert_document(connection, prepared[document_id])
            self._refresh_state(connection)

    def tombstone_memory_item(
        self,
        *,
        memory_item_id: str,
        tombstoned_at: datetime | None = None,
    ) -> None:
        self._require_open()
        item_id = _required_identifier(memory_item_id, "memory_item_id")
        with self._write_transaction() as connection:
            self._tombstone_item(
                connection,
                item_id,
                _utc_text(tombstoned_at or datetime.now(UTC)),
            )
            self._refresh_state(connection)

    def tombstone_scope(
        self,
        *,
        owner_id: str,
        world_id: str,
        subject_world_character_id: str,
        tombstoned_at: datetime | None = None,
    ) -> None:
        self._require_open()
        values = (
            _required_identifier(owner_id, "owner_id"),
            _required_identifier(world_id, "world_id"),
            _required_identifier(
                subject_world_character_id,
                "subject_world_character_id",
            ),
        )
        with self._write_transaction() as connection:
            ids = tuple(
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT document_id FROM memory_recall_documents
                    WHERE owner_id = ? AND world_id = ?
                      AND subject_world_character_id = ? AND searchable = 1
                    """,
                    values,
                )
            )
            for document_id in ids:
                connection.execute(
                    "DELETE FROM memory_recall_fts WHERE document_id = ?",
                    (document_id,),
                )
            connection.execute(
                """
                UPDATE memory_recall_documents
                SET searchable = 0, tombstoned_at = ?
                WHERE owner_id = ? AND world_id = ?
                  AND subject_world_character_id = ? AND searchable = 1
                """,
                (_utc_text(tombstoned_at or datetime.now(UTC)), *values),
            )
            self._refresh_state(connection)

    def search(
        self,
        query: MemoryRecallSearchQuery,
    ) -> tuple[MemoryRecallCandidate, ...]:
        self._require_open()
        if not 1 <= query.limit <= 50:
            raise ValueError("Memory recall limit must be between 1 and 50")
        normalized = normalize_search_text(query.text, max_chars=1_000)
        if not normalized or not query.kinds:
            return ()
        terms = _lexical_terms(normalized, query_mode=True)
        if not terms:
            return ()
        filters, parameters = _scope_filters(query)
        match_query = " AND ".join(_quote_fts_term(term) for term in terms)
        candidate_limit = min(200, max(query.limit, query.limit * 4))
        sql = f"""
            SELECT d.*, bm25(memory_recall_fts) AS rank
            FROM memory_recall_fts
            JOIN memory_recall_documents AS d
              ON d.document_id = memory_recall_fts.document_id
            WHERE memory_recall_fts MATCH ?
              AND {" AND ".join(filters)}
            ORDER BY rank ASC, d.occurred_at DESC, d.document_id ASC
            LIMIT ?
        """
        try:
            with self._connect(self.database_path) as connection:
                try:
                    rows = connection.execute(
                        sql,
                        (match_query, *parameters, candidate_limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                if not rows:
                    rows = self._fallback_rows(
                        connection,
                        filters=filters,
                        parameters=parameters,
                        terms=terms,
                        limit=candidate_limit,
                    )
        except sqlite3.DatabaseError as exc:
            raise MemoryRecallIndexError("Memory recall query failed") from exc
        return tuple(_row_to_candidate(row) for row in rows)

    def doctor(self) -> MemoryRecallDoctor:
        self._require_open()
        try:
            return self._doctor_path(self.database_path)
        except sqlite3.DatabaseError as exc:
            raise MemoryRecallIndexError("Memory recall doctor failed") from exc

    def checkpoint(self, *, truncate: bool = False) -> tuple[int, int, int]:
        self._require_open()
        mode = "TRUNCATE" if truncate else "PASSIVE"
        with self._connect(self.database_path) as connection:
            row = connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        assert row is not None
        return int(row[0]), int(row[1]), int(row[2])

    def _build_database(
        self,
        path: Path,
        documents: Iterable["_PreparedRecallDocument"],
    ) -> None:
        _remove_database_family(path)
        with self._connect(path, wal=False) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._create_schema(connection)
                for document in sorted(documents, key=lambda value: value.document_id):
                    self._insert_document(connection, document)
                self._refresh_state(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _doctor_path(self, path: Path) -> MemoryRecallDoctor:
        with self._connect(path) as connection:
            self._validate_schema(connection)
            state = connection.execute(
                """
                SELECT schema_version, generation, digest, document_count
                FROM memory_recall_projection_state WHERE singleton_key = 1
                """
            ).fetchone()
            if state is None:
                raise MemoryRecallIndexSchemaError("Memory recall state is missing")
            integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
            integrity = str(integrity_row[0]) if integrity_row else "missing"
            document_count = int(
                connection.execute(
                    "SELECT count(*) FROM memory_recall_documents"
                ).fetchone()[0]
            )
            searchable_count = int(
                connection.execute(
                    "SELECT count(*) FROM memory_recall_documents WHERE searchable = 1"
                ).fetchone()[0]
            )
            tombstone_count = document_count - searchable_count
            indexed_count = int(
                connection.execute("SELECT count(*) FROM memory_recall_fts").fetchone()[0]
            )
            missing_count = int(
                connection.execute(
                    """
                    SELECT count(*) FROM memory_recall_documents AS d
                    LEFT JOIN memory_recall_fts AS f
                      ON f.document_id = d.document_id
                     AND f.text = d.text
                     AND f.lexical_terms = d.lexical_terms
                    WHERE d.searchable = 1 AND f.document_id IS NULL
                    """
                ).fetchone()[0]
            )
            leaked_count = int(
                connection.execute(
                    """
                    SELECT count(*) FROM memory_recall_fts AS f
                    LEFT JOIN memory_recall_documents AS d
                      ON d.document_id = f.document_id AND d.searchable = 1
                    WHERE d.document_id IS NULL
                    """
                ).fetchone()[0]
            )
            try:
                connection.execute(
                    "INSERT INTO memory_recall_fts(memory_recall_fts) VALUES ('integrity-check')"
                )
                fts_integrity = "ok"
            except sqlite3.DatabaseError:
                fts_integrity = "failed"
            digest = _projection_digest(connection)
            fts5_available = _has_fts5_table(connection)
        digest_matches = digest == str(state["digest"])
        healthy = (
            int(state["schema_version"]) == MEMORY_RECALL_SCHEMA_VERSION
            and str(state["generation"]) == self.settings.generation
            and integrity.lower() == "ok"
            and fts_integrity == "ok"
            and fts5_available
            and document_count == int(state["document_count"])
            and indexed_count == searchable_count
            and missing_count == 0
            and leaked_count == 0
            and digest_matches
        )
        return MemoryRecallDoctor(
            database_path=str(path),
            generation=self.settings.generation,
            schema_version=int(state["schema_version"]),
            fts5_available=fts5_available,
            integrity_check=(
                integrity if fts_integrity == "ok" else f"{integrity};fts5=failed"
            ),
            document_count=document_count,
            searchable_document_count=searchable_count,
            indexed_document_count=indexed_count,
            tombstone_count=tombstone_count,
            digest=digest,
            digest_matches=digest_matches,
            rollback_available=self.rollback_path.exists(),
            healthy=healthy,
            tokenizer_strategy=_TOKENIZER_STRATEGY,
        )

    def _checkpoint_path(self, path: Path) -> None:
        if not path.exists():
            return
        with self._connect(path) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        _remove_sidecars(path)

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE memory_recall_projection_state (
                singleton_key INTEGER PRIMARY KEY CHECK (singleton_key = 1),
                schema_version INTEGER NOT NULL,
                generation TEXT NOT NULL,
                digest TEXT NOT NULL,
                document_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE memory_recall_documents (
                document_id TEXT PRIMARY KEY,
                memory_item_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                world_id TEXT NOT NULL,
                subject_world_character_id TEXT NOT NULL,
                counterpart_world_character_id TEXT,
                thread_id TEXT,
                kind TEXT NOT NULL,
                canonical_source_id TEXT NOT NULL,
                source_type TEXT,
                source_event_id TEXT,
                occurred_at TEXT,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                lexical_terms TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                searchable INTEGER NOT NULL CHECK (searchable IN (0, 1)),
                tombstoned_at TEXT
            )
            """,
            """
            CREATE INDEX ix_memory_recall_scope
            ON memory_recall_documents (
                owner_id, world_id, subject_world_character_id, kind, document_id
            )
            """,
            """
            CREATE INDEX ix_memory_recall_counterpart
            ON memory_recall_documents (
                owner_id, world_id, subject_world_character_id,
                counterpart_world_character_id, document_id
            )
            """,
            """
            CREATE INDEX ix_memory_recall_thread
            ON memory_recall_documents (
                owner_id, world_id, subject_world_character_id, thread_id, document_id
            )
            """,
            """
            CREATE INDEX ix_memory_recall_item
            ON memory_recall_documents (memory_item_id, searchable, document_id)
            """,
            """
            CREATE VIRTUAL TABLE memory_recall_fts USING fts5(
                document_id UNINDEXED,
                text,
                lexical_terms,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """,
        )
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            """
            INSERT INTO memory_recall_projection_state (
                singleton_key, schema_version, generation, digest,
                document_count, updated_at
            ) VALUES (1, ?, ?, ?, 0, ?)
            """,
            (
                MEMORY_RECALL_SCHEMA_VERSION,
                self.settings.generation,
                hashlib.sha256(b"").hexdigest(),
                _utc_text(datetime.now(UTC)),
            ),
        )

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        required = {
            "memory_recall_projection_state",
            "memory_recall_documents",
            "memory_recall_fts",
        }
        if not required.issubset(existing):
            raise MemoryRecallIndexSchemaError("Memory recall schema is incomplete")
        state = connection.execute(
            """
            SELECT schema_version, generation FROM memory_recall_projection_state
            WHERE singleton_key = 1
            """
        ).fetchone()
        if state is None:
            raise MemoryRecallIndexSchemaError("Memory recall state row is missing")
        if int(state["schema_version"]) != MEMORY_RECALL_SCHEMA_VERSION:
            raise MemoryRecallIndexSchemaError("Memory recall schema version mismatch")
        if str(state["generation"]) != self.settings.generation:
            raise MemoryRecallIndexSchemaError("Memory recall generation mismatch")

    @contextmanager
    def _connect(self, path: Path, *, wal: bool = True) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            path,
            timeout=self.settings.busy_timeout_ms / 1_000,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(f"PRAGMA busy_timeout = {self.settings.busy_timeout_ms}")
            connection.execute(f"PRAGMA journal_mode = {'WAL' if wal else 'DELETE'}")
            connection.execute(f"PRAGMA synchronous = {self.settings.synchronous}")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except sqlite3.DatabaseError as exc:
                connection.rollback()
                raise MemoryRecallIndexError("Memory recall write failed") from exc
            except Exception:
                connection.rollback()
                raise

    def _upsert_document(
        self,
        connection: sqlite3.Connection,
        document: "_PreparedRecallDocument",
    ) -> None:
        connection.execute(
            "DELETE FROM memory_recall_fts WHERE document_id = ?",
            (document.document_id,),
        )
        connection.execute(
            "DELETE FROM memory_recall_documents WHERE document_id = ?",
            (document.document_id,),
        )
        self._insert_document(connection, document)

    @staticmethod
    def _insert_document(
        connection: sqlite3.Connection,
        document: "_PreparedRecallDocument",
    ) -> None:
        connection.execute(
            """
            INSERT INTO memory_recall_documents (
                document_id, memory_item_id, owner_id, world_id,
                subject_world_character_id, counterpart_world_character_id,
                thread_id, kind, canonical_source_id, source_type,
                source_event_id, occurred_at, text, normalized_text,
                lexical_terms, metadata_json, searchable, tombstoned_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            document.as_values(),
        )
        if document.searchable:
            connection.execute(
                """
                INSERT INTO memory_recall_fts (document_id, text, lexical_terms)
                VALUES (?, ?, ?)
                """,
                (document.document_id, document.text, document.lexical_terms),
            )

    @staticmethod
    def _tombstone_item(
        connection: sqlite3.Connection,
        memory_item_id: str,
        tombstoned_at: str,
    ) -> None:
        ids = tuple(
            str(row[0])
            for row in connection.execute(
                """
                SELECT document_id FROM memory_recall_documents
                WHERE memory_item_id = ? AND searchable = 1
                """,
                (memory_item_id,),
            )
        )
        for document_id in ids:
            connection.execute(
                "DELETE FROM memory_recall_fts WHERE document_id = ?",
                (document_id,),
            )
        connection.execute(
            """
            UPDATE memory_recall_documents
            SET searchable = 0, tombstoned_at = ?
            WHERE memory_item_id = ? AND searchable = 1
            """,
            (tombstoned_at, memory_item_id),
        )

    @staticmethod
    def _refresh_state(connection: sqlite3.Connection) -> None:
        digest = _projection_digest(connection)
        count = int(
            connection.execute(
                "SELECT count(*) FROM memory_recall_documents"
            ).fetchone()[0]
        )
        connection.execute(
            """
            UPDATE memory_recall_projection_state
            SET digest = ?, document_count = ?, updated_at = ?
            WHERE singleton_key = 1
            """,
            (digest, count, _utc_text(datetime.now(UTC))),
        )

    @staticmethod
    def _fallback_rows(
        connection: sqlite3.Connection,
        *,
        filters: list[str],
        parameters: list[str],
        terms: tuple[str, ...],
        limit: int,
    ) -> list[sqlite3.Row]:
        rows = connection.execute(
            f"""
            SELECT d.*, 0.0 AS rank FROM memory_recall_documents AS d
            WHERE {" AND ".join(filters)}
            ORDER BY d.occurred_at DESC, d.document_id ASC
            """,
            parameters,
        ).fetchall()
        matched = [
            row
            for row in rows
            if all(
                term in str(row["normalized_text"])
                or term in str(row["lexical_terms"]).split()
                for term in terms
            )
        ]
        return matched[:limit]

    def _require_open(self) -> None:
        if not self._opened:
            raise MemoryRecallIndexError("Memory recall projection is not open")


@dataclass(frozen=True, slots=True)
class _PreparedRecallDocument:
    document_id: str
    memory_item_id: str
    owner_id: str
    world_id: str
    subject_world_character_id: str
    counterpart_world_character_id: str | None
    thread_id: str | None
    kind: str
    canonical_source_id: str
    source_type: str | None
    source_event_id: str | None
    occurred_at: str | None
    text: str
    normalized_text: str
    lexical_terms: str
    metadata_json: str
    searchable: bool
    tombstoned_at: str | None

    def as_values(self) -> tuple[object, ...]:
        return (
            self.document_id,
            self.memory_item_id,
            self.owner_id,
            self.world_id,
            self.subject_world_character_id,
            self.counterpart_world_character_id,
            self.thread_id,
            self.kind,
            self.canonical_source_id,
            self.source_type,
            self.source_event_id,
            self.occurred_at,
            self.text,
            self.normalized_text,
            self.lexical_terms,
            self.metadata_json,
            1 if self.searchable else 0,
            self.tombstoned_at,
        )


def _prepare_unique_documents(
    documents: Iterable[MemoryRecallDocument],
) -> dict[str, _PreparedRecallDocument]:
    prepared: dict[str, _PreparedRecallDocument] = {}
    for document in documents:
        value = _prepare_document(document)
        if value.document_id in prepared:
            raise ValueError(f"duplicate Memory recall document: {value.document_id}")
        prepared[value.document_id] = value
    return prepared


def _prepare_document(document: MemoryRecallDocument) -> _PreparedRecallDocument:
    text = " ".join(str(document.text or "").split())
    normalized = normalize_search_text(text, max_chars=50_000)
    if not normalized:
        raise ValueError("Memory recall document text must not be empty")
    metadata = {
        str(key): str(value)
        for key, value in sorted(document.metadata.items(), key=lambda item: str(item[0]))
    }
    return _PreparedRecallDocument(
        document_id=_required_identifier(document.document_id, "document_id"),
        memory_item_id=_required_identifier(document.memory_item_id, "memory_item_id"),
        owner_id=_required_identifier(document.owner_id, "owner_id"),
        world_id=_required_identifier(document.world_id, "world_id"),
        subject_world_character_id=_required_identifier(
            document.subject_world_character_id,
            "subject_world_character_id",
        ),
        counterpart_world_character_id=_optional_identifier(
            document.counterpart_world_character_id
        ),
        thread_id=_optional_identifier(document.thread_id),
        kind=document.kind.value,
        canonical_source_id=_required_identifier(
            document.canonical_source_id,
            "canonical_source_id",
        ),
        source_type=document.source_type.value if document.source_type else None,
        source_event_id=_optional_identifier(document.source_event_id),
        occurred_at=_utc_text(document.occurred_at) if document.occurred_at else None,
        text=text,
        normalized_text=normalized,
        lexical_terms=" ".join(_lexical_terms(normalized, query_mode=False)),
        metadata_json=json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        searchable=bool(document.searchable),
        tombstoned_at=(
            _utc_text(document.tombstoned_at) if document.tombstoned_at else None
        ),
    )


def _scope_filters(query: MemoryRecallSearchQuery) -> tuple[list[str], list[str]]:
    filters = [
        "d.searchable = 1",
        "d.owner_id = ?",
        "d.world_id = ?",
        "d.subject_world_character_id = ?",
    ]
    parameters = [
        query.scope.owner_id,
        query.scope.world_id,
        query.scope.subject_world_character_id,
    ]
    kinds = tuple(kind.value for kind in query.kinds)
    filters.append(f"d.kind IN ({', '.join('?' for _ in kinds)})")
    parameters.extend(kinds)
    if query.counterpart_world_character_id is not None:
        filters.append("d.counterpart_world_character_id = ?")
        parameters.append(query.counterpart_world_character_id)
    if query.thread_id is not None:
        filters.append("d.thread_id = ?")
        parameters.append(query.thread_id)
    return filters, parameters


def _row_to_candidate(row: sqlite3.Row) -> MemoryRecallCandidate:
    occurred_at = None
    if row["occurred_at"]:
        occurred_at = datetime.fromisoformat(str(row["occurred_at"]).replace("Z", "+00:00"))
    source_type = (
        MemorySourceTypeV1(str(row["source_type"]))
        if row["source_type"] is not None
        else None
    )
    rank = float(row["rank"])
    return MemoryRecallCandidate(
        document_id=str(row["document_id"]),
        memory_item_id=str(row["memory_item_id"]),
        kind=RecallDocumentKind(str(row["kind"])),
        canonical_source_id=str(row["canonical_source_id"]),
        score=max(0.0, -rank),
        snippet=str(row["text"])[:240],
        counterpart_world_character_id=_row_optional(
            row,
            "counterpart_world_character_id",
        ),
        thread_id=_row_optional(row, "thread_id"),
        source_type=source_type,
        source_event_id=_row_optional(row, "source_event_id"),
        occurred_at=occurred_at,
        metadata=json.loads(str(row["metadata_json"])),
    )


def _projection_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    rows = connection.execute(
        """
        SELECT document_id, memory_item_id, owner_id, world_id,
               subject_world_character_id, counterpart_world_character_id,
               thread_id, kind, canonical_source_id, source_type,
               source_event_id, occurred_at, text, normalized_text,
               lexical_terms, metadata_json, searchable, tombstoned_at
        FROM memory_recall_documents ORDER BY document_id
        """
    )
    for row in rows:
        digest.update(
            json.dumps(
                [row[key] for key in row.keys()],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _lexical_terms(value: str, *, query_mode: bool) -> tuple[str, ...]:
    terms: list[str] = []
    for token in _WORD_PATTERN.findall(value):
        if _contains_cjk(token):
            cjk = "".join(character for character in token if _is_cjk(character))
            if len(cjk) == 1:
                terms.append(cjk)
            elif len(cjk) > 1:
                if not query_mode:
                    terms.append(cjk)
                terms.extend(cjk[index : index + 2] for index in range(len(cjk) - 1))
            non_cjk = "".join(
                character if not _is_cjk(character) else " " for character in token
            )
            terms.extend(_WORD_PATTERN.findall(non_cjk))
        else:
            terms.append(token)
    return tuple(dict.fromkeys(term for term in terms if term))


def _contains_cjk(value: str) -> bool:
    return any(_is_cjk(character) for character in value)


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x9FFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def _quote_fts_term(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _required_identifier(value: object, field_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > 500:
        raise ValueError(f"{field_name} is too long")
    return normalized


def _optional_identifier(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    return normalized or None


def _row_optional(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    return str(value) if value is not None else None


def _has_fts5_table(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'memory_recall_fts'"
    ).fetchone()
    return bool(row and "fts5" in str(row[0]).casefold())


def _remove_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            candidate.unlink()


def _remove_database_family(path: Path) -> None:
    _remove_sidecars(path)
    if path.exists():
        path.unlink()


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "MemoryRecallIndexError",
    "MemoryRecallIndexSchemaError",
    "MemoryRecallIndexSettings",
    "SqliteMemoryRecallIndex",
]
