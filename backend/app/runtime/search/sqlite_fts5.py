"""Rebuildable SQLite FTS5 projection for the embedded local runtime."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
import unicodedata

from app.core.search_text import normalize_search_text
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort
from app.domains.runtime.ports.search_index import (
    SearchIndexDoctor,
    SearchIndexDocument,
    SearchIndexHit,
    SearchIndexQuery,
)


_SCHEMA_VERSION = 1
_GENERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_WORD_PATTERN = re.compile(r"[\w]+", re.UNICODE)
_TOKENIZER_STRATEGY = "unicode61 + CJK bigram terms + normalized substring fallback"


class SqliteFts5Error(RuntimeError):
    pass


class SqliteFts5SchemaError(SqliteFts5Error):
    pass


@dataclass(frozen=True)
class SqliteFts5Settings:
    generation: str = "v1"
    busy_timeout_ms: int = 5_000
    synchronous: str = "FULL"

    def __post_init__(self) -> None:
        if not _GENERATION_PATTERN.fullmatch(self.generation):
            raise ValueError("invalid FTS5 generation")
        if self.busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        if self.synchronous not in {"NORMAL", "FULL"}:
            raise ValueError("synchronous must be NORMAL or FULL")


class SqliteFts5SearchIndex:
    """Own a non-canonical FTS5 file that can be rebuilt from source records."""

    def __init__(
        self,
        data_paths: RuntimeDataPathPort,
        *,
        settings: SqliteFts5Settings | None = None,
    ) -> None:
        self.settings = settings or SqliteFts5Settings()
        paths = data_paths.resolve()
        self.database_path = (
            paths.search
            / "generations"
            / self.settings.generation
            / "angmoo-search.sqlite3"
        )
        self._opened = False
        self._lock = RLock()

    def open(self) -> SearchIndexDoctor:
        with self._lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                self._initialize_or_validate(connection)
            self._opened = True
            return self.doctor()

    def close(self) -> None:
        self._opened = False

    def upsert(self, document: SearchIndexDocument) -> None:
        self._require_open()
        prepared = _prepare_document(document)
        if prepared is None:
            self.remove(document_id=document.document_id)
            return
        with self._write_transaction() as connection:
            self._delete_document(connection, document.document_id)
            self._insert_document(connection, prepared)
            self._refresh_state(connection)

    def remove(self, *, document_id: str) -> None:
        self._require_open()
        document_id = _required_identifier(document_id, field_name="document_id")
        with self._write_transaction() as connection:
            self._delete_document(connection, document_id)
            self._refresh_state(connection)

    def search(
        self,
        *,
        world_id: str,
        query: str,
        limit: int,
    ) -> tuple[SearchIndexHit, ...]:
        return self.search_scoped(
            SearchIndexQuery(world_id=world_id, text=query, limit=limit)
        )

    def search_scoped(self, query: SearchIndexQuery) -> tuple[SearchIndexHit, ...]:
        self._require_open()
        world_id = _required_identifier(query.world_id, field_name="world_id")
        if not 1 <= query.limit <= 100:
            raise ValueError("search limit must be between 1 and 100")
        normalized_query = normalize_search_text(query.text, max_chars=1_000)
        if not normalized_query:
            return ()
        terms = _lexical_terms(normalized_query, query_mode=True)
        if not terms:
            return ()

        filters, parameters = _scope_filters(query, world_id=world_id)
        match_query = " AND ".join(_quote_fts_term(term) for term in terms)
        sql = f"""
            SELECT d.*, bm25(search_documents_fts) AS rank
            FROM search_documents_fts
            JOIN search_documents AS d
              ON d.document_id = search_documents_fts.document_id
            WHERE search_documents_fts MATCH ?
              AND {" AND ".join(filters)}
            ORDER BY rank ASC, d.occurred_at DESC, d.document_id ASC
            LIMIT ?
        """
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    sql,
                    (match_query, *parameters, query.limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                rows = self._fallback_rows(
                    connection,
                    query=query,
                    world_id=world_id,
                    terms=terms,
                )
        return tuple(_row_to_hit(row) for row in rows)

    def rebuild(self, documents: Iterable[SearchIndexDocument]) -> SearchIndexDoctor:
        self._require_open()
        prepared_by_id: dict[str, _PreparedDocument] = {}
        seen: set[str] = set()
        for document in documents:
            document_id = _required_identifier(
                document.document_id, field_name="document_id"
            )
            if document_id in seen:
                raise ValueError(f"duplicate search document: {document_id}")
            seen.add(document_id)
            prepared = _prepare_document(document)
            if prepared is not None:
                prepared_by_id[document_id] = prepared

        with self._write_transaction() as connection:
            connection.execute("DELETE FROM search_documents_fts")
            connection.execute("DELETE FROM search_documents")
            for document_id in sorted(prepared_by_id):
                self._insert_document(connection, prepared_by_id[document_id])
            self._refresh_state(connection)
        return self.doctor()

    def doctor(self) -> SearchIndexDoctor:
        self._require_open()
        with self._connect() as connection:
            state = connection.execute(
                """
                SELECT schema_version, generation, digest, document_count
                FROM search_projection_state
                WHERE singleton_key = 1
                """
            ).fetchone()
            if state is None:
                raise SqliteFts5SchemaError("FTS5 projection state is missing")
            integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
            integrity = str(integrity_row[0]) if integrity_row else "missing"
            document_count = int(
                connection.execute("SELECT count(*) FROM search_documents").fetchone()[0]
            )
            indexed_count = int(
                connection.execute(
                    "SELECT count(*) FROM search_documents_fts"
                ).fetchone()[0]
            )
            mirror_mismatch_count = int(
                connection.execute(
                    """
                    SELECT count(*)
                    FROM search_documents AS d
                    LEFT JOIN search_documents_fts AS f
                      ON f.document_id = d.document_id
                     AND f.text = d.text
                     AND f.lexical_terms = d.lexical_terms
                    WHERE f.document_id IS NULL
                    """
                ).fetchone()[0]
            )
            try:
                connection.execute(
                    """
                    INSERT INTO search_documents_fts(search_documents_fts)
                    VALUES ('integrity-check')
                    """
                )
                fts_integrity = "ok"
            except sqlite3.DatabaseError:
                fts_integrity = "failed"
            digest = _projection_digest(connection)
            fts5_available = _has_fts5_table(connection)
        digest_matches = digest == str(state["digest"])
        healthy = (
            int(state["schema_version"]) == _SCHEMA_VERSION
            and str(state["generation"]) == self.settings.generation
            and integrity.lower() == "ok"
            and fts5_available
            and document_count == indexed_count == int(state["document_count"])
            and mirror_mismatch_count == 0
            and fts_integrity == "ok"
            and digest_matches
        )
        return SearchIndexDoctor(
            database_path=str(self.database_path),
            generation=self.settings.generation,
            schema_version=int(state["schema_version"]),
            fts5_available=fts5_available,
            integrity_check=(
                integrity if fts_integrity == "ok" else f"{integrity};fts5=failed"
            ),
            document_count=document_count,
            indexed_document_count=indexed_count,
            digest=digest,
            digest_matches=digest_matches,
            healthy=healthy,
            tokenizer_strategy=_TOKENIZER_STRATEGY,
        )

    def checkpoint(self, *, truncate: bool = False) -> tuple[int, int, int]:
        self._require_open()
        mode = "TRUNCATE" if truncate else "PASSIVE"
        with self._connect() as connection:
            row = connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        assert row is not None
        return int(row[0]), int(row[1]), int(row[2])

    def _initialize_or_validate(self, connection: sqlite3.Connection) -> None:
        state_exists = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'search_projection_state'
            """
        ).fetchone()
        if state_exists is None:
            user_tables = {
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            if user_tables:
                raise SqliteFts5SchemaError(
                    "unversioned FTS5 projection is not accepted"
                )
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._create_schema(connection)
                self._refresh_state(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return
        state = connection.execute(
            """
            SELECT schema_version, generation
            FROM search_projection_state
            WHERE singleton_key = 1
            """
        ).fetchone()
        if state is None:
            raise SqliteFts5SchemaError("FTS5 projection state row is missing")
        if int(state["schema_version"]) != _SCHEMA_VERSION:
            raise SqliteFts5SchemaError("unsupported FTS5 projection schema version")
        if str(state["generation"]) != self.settings.generation:
            raise SqliteFts5SchemaError("FTS5 projection generation does not match")
        required = {"search_documents", "search_documents_fts"}
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        if not required.issubset(existing):
            raise SqliteFts5SchemaError("FTS5 projection schema is incomplete")

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE search_projection_state (
                singleton_key INTEGER PRIMARY KEY CHECK (singleton_key = 1),
                schema_version INTEGER NOT NULL,
                generation TEXT NOT NULL,
                digest TEXT NOT NULL,
                document_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE search_documents (
                document_id TEXT PRIMARY KEY,
                world_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                character_id TEXT,
                counterparty_id TEXT,
                source_id TEXT NOT NULL,
                source_event_id TEXT,
                occurred_at TEXT,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                lexical_terms TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX ix_search_documents_world
                ON search_documents (world_id, kind, document_id)
            """,
            """
            CREATE INDEX ix_search_documents_character
                ON search_documents (world_id, character_id, document_id)
            """,
            """
            CREATE INDEX ix_search_documents_counterparty
                ON search_documents (world_id, counterparty_id, document_id)
            """,
            """
            CREATE VIRTUAL TABLE search_documents_fts USING fts5(
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
            INSERT INTO search_projection_state (
                singleton_key, schema_version, generation, digest,
                document_count, updated_at
            ) VALUES (1, ?, ?, ?, 0, ?)
            """,
            (
                _SCHEMA_VERSION,
                self.settings.generation,
                hashlib.sha256(b"").hexdigest(),
                _utc_now_text(),
            ),
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.settings.busy_timeout_ms / 1_000,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(f"PRAGMA busy_timeout = {self.settings.busy_timeout_ms}")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(f"PRAGMA synchronous = {self.settings.synchronous}")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _insert_document(
        self, connection: sqlite3.Connection, document: _PreparedDocument
    ) -> None:
        values = document.as_values()
        connection.execute(
            """
            INSERT INTO search_documents (
                document_id, world_id, kind, character_id, counterparty_id,
                source_id, source_event_id, occurred_at, text, normalized_text,
                lexical_terms, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        connection.execute(
            """
            INSERT INTO search_documents_fts (document_id, text, lexical_terms)
            VALUES (?, ?, ?)
            """,
            (document.document_id, document.text, document.lexical_terms),
        )

    @staticmethod
    def _delete_document(connection: sqlite3.Connection, document_id: str) -> None:
        connection.execute(
            "DELETE FROM search_documents_fts WHERE document_id = ?", (document_id,)
        )
        connection.execute(
            "DELETE FROM search_documents WHERE document_id = ?", (document_id,)
        )

    @staticmethod
    def _refresh_state(connection: sqlite3.Connection) -> None:
        digest = _projection_digest(connection)
        count = int(connection.execute("SELECT count(*) FROM search_documents").fetchone()[0])
        connection.execute(
            """
            UPDATE search_projection_state
            SET digest = ?, document_count = ?, updated_at = ?
            WHERE singleton_key = 1
            """,
            (digest, count, _utc_now_text()),
        )

    def _fallback_rows(
        self,
        connection: sqlite3.Connection,
        *,
        query: SearchIndexQuery,
        world_id: str,
        terms: tuple[str, ...],
    ) -> list[sqlite3.Row]:
        filters, parameters = _scope_filters(query, world_id=world_id)
        rows = connection.execute(
            f"""
            SELECT d.*, 0.0 AS rank
            FROM search_documents AS d
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
        return matched[: query.limit]

    def _require_open(self) -> None:
        if not self._opened:
            raise SqliteFts5Error("FTS5 projection is not open")


@dataclass(frozen=True)
class _PreparedDocument:
    document_id: str
    world_id: str
    kind: str
    character_id: str | None
    counterparty_id: str | None
    source_id: str
    source_event_id: str | None
    occurred_at: str | None
    text: str
    normalized_text: str
    lexical_terms: str
    metadata_json: str

    def as_values(self) -> tuple[str | None, ...]:
        return (
            self.document_id,
            self.world_id,
            self.kind,
            self.character_id,
            self.counterparty_id,
            self.source_id,
            self.source_event_id,
            self.occurred_at,
            self.text,
            self.normalized_text,
            self.lexical_terms,
            self.metadata_json,
        )


def _prepare_document(document: SearchIndexDocument) -> _PreparedDocument | None:
    document_id = _required_identifier(document.document_id, field_name="document_id")
    if not document.searchable:
        return None
    world_id = _required_identifier(document.world_id, field_name="world_id")
    kind = _required_identifier(document.kind, field_name="kind")
    text = str(document.text or "").strip()
    normalized = normalize_search_text(text, max_chars=50_000)
    if not normalized:
        raise ValueError("search document text must not be empty")
    metadata = {
        str(key): str(value)
        for key, value in sorted(document.metadata.items(), key=lambda item: str(item[0]))
    }
    source_id = _required_identifier(
        document.source_id or document_id, field_name="source_id"
    )
    return _PreparedDocument(
        document_id=document_id,
        world_id=world_id,
        kind=kind,
        character_id=_optional_identifier(document.character_id),
        counterparty_id=_optional_identifier(document.counterparty_id),
        source_id=source_id,
        source_event_id=_optional_identifier(document.source_event_id),
        occurred_at=_optional_identifier(document.occurred_at),
        text=text,
        normalized_text=normalized,
        lexical_terms=" ".join(_lexical_terms(normalized, query_mode=False)),
        metadata_json=json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _scope_filters(
    query: SearchIndexQuery, *, world_id: str
) -> tuple[list[str], list[str]]:
    filters = ["d.world_id = ?"]
    parameters = [world_id]
    if query.character_id is not None:
        filters.append("d.character_id = ?")
        parameters.append(
            _required_identifier(query.character_id, field_name="character_id")
        )
    if query.counterparty_id is not None:
        filters.append("d.counterparty_id = ?")
        parameters.append(
            _required_identifier(query.counterparty_id, field_name="counterparty_id")
        )
    if query.kinds:
        kinds = tuple(_required_identifier(kind, field_name="kind") for kind in query.kinds)
        filters.append(f"d.kind IN ({', '.join('?' for _ in kinds)})")
        parameters.extend(kinds)
    return filters, parameters


def _row_to_hit(row: sqlite3.Row) -> SearchIndexHit:
    rank = float(row["rank"])
    return SearchIndexHit(
        document_id=str(row["document_id"]),
        score=max(0.0, -rank),
        snippet=str(row["text"])[:240],
        world_id=str(row["world_id"]),
        kind=str(row["kind"]),
        character_id=_row_optional(row, "character_id"),
        counterparty_id=_row_optional(row, "counterparty_id"),
        source_id=str(row["source_id"]),
        source_event_id=_row_optional(row, "source_event_id"),
        occurred_at=_row_optional(row, "occurred_at"),
        metadata=json.loads(str(row["metadata_json"])),
    )


def _projection_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    rows = connection.execute(
        """
        SELECT document_id, world_id, kind, character_id, counterparty_id,
               source_id, source_event_id, occurred_at, text, normalized_text,
               lexical_terms, metadata_json
        FROM search_documents
        ORDER BY document_id
        """
    )
    for row in rows:
        payload = [row[key] for key in row.keys()]
        digest.update(
            json.dumps(
                payload,
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
            cjk_characters = "".join(character for character in token if _is_cjk(character))
            if len(cjk_characters) == 1:
                terms.append(cjk_characters)
            elif len(cjk_characters) > 1:
                if not query_mode:
                    terms.append(cjk_characters)
                terms.extend(
                    cjk_characters[index : index + 2]
                    for index in range(len(cjk_characters) - 1)
                )
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


def _required_identifier(value: object, *, field_name: str) -> str:
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
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'search_documents_fts'
        """
    ).fetchone()
    return bool(row and "fts5" in str(row[0]).casefold())


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "SqliteFts5Error",
    "SqliteFts5SchemaError",
    "SqliteFts5SearchIndex",
    "SqliteFts5Settings",
]
