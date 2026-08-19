"""OFF-by-default SQLite canonical database adapter for ER2 validation."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import re
from typing import Any

from sqlalchemy import Engine, URL, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.domains.runtime.ports.runtime_data_path import (
    RuntimeDataPathPort,
    RuntimeDataPaths,
)
from app.runtime.persistence.sqlite_codecs import (
    decode_json_document,
    encode_json_document,
    encode_utc_timestamp,
)
from app.runtime.persistence.sqlite_schema import (
    EXPECTED_CANONICAL_TABLE_COUNT,
    SCHEMA_VERSION_TABLE,
    SOURCE_ALEMBIC_MIGRATION_COUNT,
    SOURCE_ALEMBIC_REVISION,
    SQLITE_SCHEMA_VERSION,
    build_sqlite_baseline_metadata,
    create_schema_version_table,
    sqlite_schema_digest,
)


_GENERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SqliteCanonicalError(RuntimeError):
    pass


class SqliteSchemaMismatchError(SqliteCanonicalError):
    pass


@dataclass(frozen=True)
class SqliteCanonicalSettings:
    generation: str = "v1"
    busy_timeout_ms: int = 5_000
    synchronous: str = "FULL"
    wal_autocheckpoint_pages: int = 1_000
    page_size: int = 4_096

    def __post_init__(self) -> None:
        if not _GENERATION_PATTERN.fullmatch(self.generation):
            raise ValueError("invalid SQLite generation")
        if self.busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        if self.synchronous not in {"NORMAL", "FULL"}:
            raise ValueError("synchronous must be NORMAL or FULL")
        if self.wal_autocheckpoint_pages < 1:
            raise ValueError("wal_autocheckpoint_pages must be positive")
        if self.page_size not in {4_096, 8_192, 16_384}:
            raise ValueError("unsupported SQLite page size")


@dataclass(frozen=True)
class SqliteCanonicalDoctor:
    database_path: str
    generation: str
    schema_version: int
    source_revision: str
    source_migration_count: int
    schema_digest: str
    schema_digest_matches: bool
    canonical_table_count: int
    foreign_keys: bool
    journal_mode: str
    synchronous: str
    busy_timeout_ms: int
    wal_autocheckpoint_pages: int
    page_size: int


class LocalAppDataRuntimeDataPath:
    """Side-effect-free OS data-root resolver for the future installed runtime."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        home: Path | None = None,
        os_name: str | None = None,
    ) -> None:
        self._environ = dict(environ if environ is not None else os.environ)
        self._home = (home or Path.home()).expanduser()
        self._os_name = os_name or os.name

    def resolve(self) -> RuntimeDataPaths:
        if self._os_name == "nt":
            local_app_data = self._environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise SqliteCanonicalError("LOCALAPPDATA is unavailable")
            root = Path(local_app_data).expanduser() / "Angmoo"
        else:
            root = Path(
                self._environ.get("XDG_DATA_HOME", self._home / ".local" / "share")
            ).expanduser() / "angmoo"
        root = root.resolve()
        return RuntimeDataPaths(
            root=root,
            canonical=root / "canonical",
            graph=root / "graph",
            search=root / "search",
            media=root / "media",
            secrets=root / "secrets",
        )


class SqliteCanonicalDatabase:
    """Own one file-backed SQLite engine and its embedded schema lineage."""

    def __init__(
        self,
        data_paths: RuntimeDataPathPort,
        *,
        settings: SqliteCanonicalSettings | None = None,
    ) -> None:
        self._data_paths = data_paths
        self.settings = settings or SqliteCanonicalSettings()
        paths = data_paths.resolve()
        self.database_path = (
            paths.canonical
            / "generations"
            / self.settings.generation
            / "angmoo.sqlite3"
        )
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise SqliteCanonicalError("SQLite canonical database is not open")
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            raise SqliteCanonicalError("SQLite canonical database is not open")
        return self._session_factory

    def open(self) -> SqliteCanonicalDoctor:
        if self._engine is not None:
            return self.doctor()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(self.database_path)),
            connect_args={"check_same_thread": False},
            json_serializer=encode_json_document,
            json_deserializer=decode_json_document,
            pool_pre_ping=True,
        )
        _configure_sqlite_engine(engine, self.settings)
        self._engine = engine
        self._session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
        )
        try:
            self._initialize_or_validate()
            doctor = self.doctor()
            self._validate_doctor(doctor)
            return doctor
        except Exception:
            self.close()
            raise

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def checkpoint(self, *, truncate: bool = False) -> tuple[int, int, int]:
        mode = "TRUNCATE" if truncate else "PASSIVE"
        with self.engine.connect() as connection:
            row = connection.exec_driver_sql(
                f"PRAGMA wal_checkpoint({mode})"
            ).one()
        return int(row[0]), int(row[1]), int(row[2])

    def doctor(self) -> SqliteCanonicalDoctor:
        with self.engine.connect() as connection:
            row = connection.exec_driver_sql(
                f"""
                SELECT schema_version, source_revision, source_migration_count,
                       schema_digest
                FROM {SCHEMA_VERSION_TABLE}
                WHERE singleton_key = 1
                """
            ).mappings().one()
            current_digest = sqlite_schema_digest(connection)
            canonical_table_count = int(
                connection.exec_driver_sql(
                    """
                    SELECT count(*) FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                      AND name != ?
                    """,
                    (SCHEMA_VERSION_TABLE,),
                ).scalar_one()
            )
            pragmas = {
                name: connection.exec_driver_sql(f"PRAGMA {name}").scalar_one()
                for name in (
                    "foreign_keys",
                    "journal_mode",
                    "synchronous",
                    "busy_timeout",
                    "wal_autocheckpoint",
                    "page_size",
                )
            }
        synchronous = {1: "NORMAL", 2: "FULL"}.get(
            int(pragmas["synchronous"]), str(pragmas["synchronous"])
        )
        return SqliteCanonicalDoctor(
            database_path=str(self.database_path),
            generation=self.settings.generation,
            schema_version=int(row["schema_version"]),
            source_revision=str(row["source_revision"]),
            source_migration_count=int(row["source_migration_count"]),
            schema_digest=str(row["schema_digest"]),
            schema_digest_matches=str(row["schema_digest"]) == current_digest,
            canonical_table_count=canonical_table_count,
            foreign_keys=bool(pragmas["foreign_keys"]),
            journal_mode=str(pragmas["journal_mode"]).upper(),
            synchronous=synchronous,
            busy_timeout_ms=int(pragmas["busy_timeout"]),
            wal_autocheckpoint_pages=int(pragmas["wal_autocheckpoint"]),
            page_size=int(pragmas["page_size"]),
        )

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self._session_factory = None

    def _initialize_or_validate(self) -> None:
        with self.engine.begin() as connection:
            user_tables = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            if SCHEMA_VERSION_TABLE not in user_tables:
                if user_tables:
                    raise SqliteSchemaMismatchError(
                        "unversioned SQLite canonical schema is not accepted"
                    )
                create_schema_version_table(connection)
                build_sqlite_baseline_metadata().create_all(connection)
                digest = sqlite_schema_digest(connection)
                connection.exec_driver_sql(
                    f"""
                    INSERT INTO {SCHEMA_VERSION_TABLE} (
                        singleton_key, schema_version, source_revision,
                        source_migration_count, schema_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        SQLITE_SCHEMA_VERSION,
                        SOURCE_ALEMBIC_REVISION,
                        SOURCE_ALEMBIC_MIGRATION_COUNT,
                        digest,
                        encode_utc_timestamp(datetime.now(UTC)),
                    ),
                )
                return
            row = connection.exec_driver_sql(
                f"""
                SELECT schema_version, source_revision, source_migration_count,
                       schema_digest
                FROM {SCHEMA_VERSION_TABLE}
                WHERE singleton_key = 1
                """
            ).mappings().one_or_none()
            if row is None:
                raise SqliteSchemaMismatchError("schema version row is missing")
            if int(row["schema_version"]) != SQLITE_SCHEMA_VERSION:
                raise SqliteSchemaMismatchError(
                    "unsupported SQLite schema version: "
                    f"{row['schema_version']}"
                )
            if str(row["source_revision"]) != SOURCE_ALEMBIC_REVISION:
                raise SqliteSchemaMismatchError("source revision does not match")
            if int(row["source_migration_count"]) != SOURCE_ALEMBIC_MIGRATION_COUNT:
                raise SqliteSchemaMismatchError("migration lineage count does not match")
            current_digest = sqlite_schema_digest(connection)
            if str(row["schema_digest"]) != current_digest:
                raise SqliteSchemaMismatchError("SQLite schema digest does not match")

    def _validate_doctor(self, doctor: SqliteCanonicalDoctor) -> None:
        expected = {
            "schema_digest_matches": True,
            "canonical_table_count": EXPECTED_CANONICAL_TABLE_COUNT,
            "foreign_keys": True,
            "journal_mode": "WAL",
            "synchronous": self.settings.synchronous,
            "busy_timeout_ms": self.settings.busy_timeout_ms,
            "wal_autocheckpoint_pages": self.settings.wal_autocheckpoint_pages,
            "page_size": self.settings.page_size,
        }
        actual = {
            name: getattr(doctor, name)
            for name in expected
        }
        mismatches = {
            name: {"expected": expected[name], "actual": actual[name]}
            for name in expected
            if actual[name] != expected[name]
        }
        if mismatches:
            details = ", ".join(
                f"{name}={values['actual']} (expected {values['expected']})"
                for name, values in sorted(mismatches.items())
            )
            raise SqliteSchemaMismatchError(
                f"SQLite canonical connection contract does not match: {details}"
            )


def _configure_sqlite_engine(
    engine: Engine, settings: SqliteCanonicalSettings
) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(f"PRAGMA busy_timeout = {settings.busy_timeout_ms}")
            cursor.execute(f"PRAGMA page_size = {settings.page_size}")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute(f"PRAGMA synchronous = {settings.synchronous}")
            cursor.execute(
                "PRAGMA wal_autocheckpoint = "
                f"{settings.wal_autocheckpoint_pages}"
            )
        finally:
            cursor.close()


__all__ = [
    "LocalAppDataRuntimeDataPath",
    "SqliteCanonicalDatabase",
    "SqliteCanonicalDoctor",
    "SqliteCanonicalError",
    "SqliteCanonicalSettings",
    "SqliteSchemaMismatchError",
]
