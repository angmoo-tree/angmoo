"""Forward-only, copy-on-write embedded SQLite generation upgrades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from sqlalchemy import URL, create_engine

from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort
from app.runtime.migrations.generation import (
    EmbeddedGenerationController,
    EmbeddedGenerationError,
)
from app.runtime.migrations.sqlite_versions.registry import (
    SqliteMigration,
    SqliteVersionManifest,
    load_sqlite_manifest,
    migration_contract,
    migration_chain,
)
from app.runtime.migrations.sqlite_versions.contracts import (
    SqliteMigrationDeltaError,
)
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    SQLITE_SCHEMA_VERSION,
    sqlite_schema_contract_digest,
    sqlite_schema_digest,
)


class SqliteCanonicalUpgradeError(RuntimeError):
    """Privacy-safe canonical upgrade failure."""


@dataclass(frozen=True)
class SqliteCanonicalUpgradeResult:
    generation: str
    database_path: Path
    source_version: int
    target_version: int
    migrated: bool
    manifest_sha256: str


@dataclass(frozen=True)
class _TableIdentity:
    row_count: int
    content_sha256: str


class SqliteCanonicalUpgradeCoordinator:
    def __init__(
        self,
        data_paths: RuntimeDataPathPort,
        *,
        fallback_generation: str,
    ) -> None:
        self._data_paths = data_paths
        self._paths = data_paths.resolve()
        self._fallback_generation = fallback_generation
        self._controller = EmbeddedGenerationController(
            self._paths.canonical,
            artifact_relative_path="angmoo.sqlite3",
        )

    def upgrade(self) -> SqliteCanonicalUpgradeResult:
        latest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
        relative = self._controller.selected_relative_path(
            f"generations/{self._fallback_generation}"
        )
        source_root = (self._paths.canonical / relative).resolve()
        source_database = source_root / "angmoo.sqlite3"
        if not source_database.is_file():
            return self._create_clean_generation(relative, latest)

        current = _inspect_database(source_database)
        if current.schema_version > SQLITE_SCHEMA_VERSION:
            raise SqliteCanonicalUpgradeError(
                "sqlite_schema_newer_than_runtime"
            )
        if current.schema_version == SQLITE_SCHEMA_VERSION:
            _validate_database(source_database, latest)
            marker = self._controller.current()
            if (
                marker is None
                or marker["relative_path"] != relative
                or marker["manifest_sha256"] != latest.manifest_sha256
                or int(marker.get("data_version", 0)) != latest.schema_version
            ):
                self._controller.promote(
                    relative,
                    manifest_sha256=latest.manifest_sha256,
                    data_version=latest.schema_version,
                )
            return SqliteCanonicalUpgradeResult(
                generation=source_root.name,
                database_path=source_database,
                source_version=current.schema_version,
                target_version=latest.schema_version,
                migrated=False,
                manifest_sha256=latest.manifest_sha256,
            )

        source_manifest = load_sqlite_manifest(current.schema_version)
        _validate_database(source_database, source_manifest)
        chain = migration_chain(current.schema_version)
        if not chain:
            raise SqliteCanonicalUpgradeError("sqlite_migration_registry_gap")
        _require_staging_capacity(source_database, self._paths.canonical)
        source_fingerprint = _database_file_fingerprint(source_database)
        final_generation = _target_generation_name(
            source_root.name,
            latest.schema_version,
        )
        final_relative = f"generations/{final_generation}"
        final_root = self._paths.canonical / final_relative
        if final_root.exists():
            final_generation = (
                f"{final_generation}-{uuid4().hex[:8]}"[:64]
            )
            final_relative = f"generations/{final_generation}"
        staging = (
            self._controller.generations
            / f".{final_generation}.tmp-{uuid4().hex[:8]}"
        )
        staging.mkdir(parents=True, exist_ok=False)
        staging_database = staging / "angmoo.sqlite3"
        try:
            _backup_database(source_database, staging_database)
            _apply_chain(staging_database, chain)
            _validate_database(staging_database, latest)
            if _database_file_fingerprint(source_database) != source_fingerprint:
                raise SqliteCanonicalUpgradeError(
                    "sqlite_migration_previous_generation_changed"
                )
            final_root = self._controller.finalize_staging(
                staging,
                final_relative,
            )
            self._controller.promote(
                final_relative,
                manifest_sha256=latest.manifest_sha256,
                data_version=latest.schema_version,
                previous_relative_path=relative,
                previous_manifest_sha256=source_manifest.manifest_sha256,
                previous_data_version=source_manifest.schema_version,
            )
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        promoted_database = final_root / "angmoo.sqlite3"
        _validate_database(promoted_database, latest)
        return SqliteCanonicalUpgradeResult(
            generation=final_root.name,
            database_path=promoted_database,
            source_version=current.schema_version,
            target_version=latest.schema_version,
            migrated=True,
            manifest_sha256=latest.manifest_sha256,
        )

    def _create_clean_generation(
        self,
        relative: str,
        latest: SqliteVersionManifest,
    ) -> SqliteCanonicalUpgradeResult:
        generation = Path(relative).name
        database = SqliteCanonicalDatabase(
            self._data_paths,
            settings=SqliteCanonicalSettings(generation=generation),
        )
        doctor = database.open()
        database.close()
        if doctor.schema_version != latest.schema_version:
            raise SqliteCanonicalUpgradeError("sqlite_schema_manifest_mismatch")
        self._controller.promote(
            relative,
            manifest_sha256=latest.manifest_sha256,
            data_version=latest.schema_version,
        )
        return SqliteCanonicalUpgradeResult(
            generation=generation,
            database_path=Path(doctor.database_path),
            source_version=latest.schema_version,
            target_version=latest.schema_version,
            migrated=False,
            manifest_sha256=latest.manifest_sha256,
        )


def _inspect_database(path: Path) -> SqliteVersionManifest:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            f"SELECT schema_version, source_revision, "
            f"source_migration_count, schema_digest "
            f"FROM {SCHEMA_VERSION_TABLE} WHERE singleton_key = 1"
        ).fetchone()
        if row is None:
            raise SqliteCanonicalUpgradeError("sqlite_schema_version_missing")
        table_inventory = tuple(
            str(item[0])
            for item in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "AND name != ? ORDER BY name",
                (SCHEMA_VERSION_TABLE,),
            )
        )
        return SqliteVersionManifest(
            schema_version=int(row[0]),
            canonical_table_count=len(table_inventory),
            schema_digest=str(row[3]),
            table_inventory=table_inventory,
            source_revision=str(row[1]),
            source_migration_count=int(row[2]),
        )
    except sqlite3.DatabaseError as exc:
        raise SqliteCanonicalUpgradeError("sqlite_schema_version_invalid") from exc
    finally:
        connection.close()


def _validate_database(path: Path, manifest: SqliteVersionManifest) -> None:
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(path)))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            row = connection.exec_driver_sql(
                f"SELECT schema_version, source_revision, "
                f"source_migration_count, schema_digest "
                f"FROM {SCHEMA_VERSION_TABLE} WHERE singleton_key = 1"
            ).one()
            inventory = tuple(
                str(item[0])
                for item in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                    "AND name != ? ORDER BY name",
                    (SCHEMA_VERSION_TABLE,),
                )
            )
            integrity = str(
                connection.exec_driver_sql("PRAGMA integrity_check").scalar_one()
            )
            foreign_key_rows = list(
                connection.exec_driver_sql("PRAGMA foreign_key_check")
            )
            actual_digest = sqlite_schema_digest(connection)
            contract_digest = sqlite_schema_contract_digest(connection)
    finally:
        engine.dispose()
    if (
        int(row[0]) != manifest.schema_version
        or str(row[1]) != manifest.source_revision
        or int(row[2]) != manifest.source_migration_count
        or inventory != manifest.table_inventory
        or contract_digest != manifest.schema_digest
        or str(row[3]) != actual_digest
    ):
        raise SqliteCanonicalUpgradeError("sqlite_schema_manifest_mismatch")
    if integrity.lower() != "ok":
        raise SqliteCanonicalUpgradeError("sqlite_integrity_check_failed")
    if foreign_key_rows:
        raise SqliteCanonicalUpgradeError("sqlite_foreign_key_check_failed")


def _apply_chain(
    path: Path,
    chain: tuple[tuple[int, SqliteMigration], ...],
) -> None:
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(path)))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            for source_version, migration in chain:
                contract = migration_contract(source_version)
                protected_identity = _connection_identity(
                    connection,
                    excluded_tables=set(contract.mutable_identity_tables),
                )
                snapshot = contract.capture(connection)
                migration(connection)
                contract.verify(connection, snapshot)
                if _connection_identity(
                    connection,
                    excluded_tables=set(contract.mutable_identity_tables),
                ) != protected_identity:
                    raise SqliteCanonicalUpgradeError(
                        "sqlite_migration_identity_changed"
                    )
                target = load_sqlite_manifest(source_version + 1)
                contract_digest = sqlite_schema_contract_digest(connection)
                if contract_digest != target.schema_digest:
                    raise SqliteCanonicalUpgradeError(
                        "sqlite_schema_manifest_mismatch"
                    )
                connection.exec_driver_sql(
                    f"UPDATE {SCHEMA_VERSION_TABLE} "
                    "SET schema_version = ?, source_revision = ?, "
                    "source_migration_count = ?, schema_digest = ?, "
                    "created_at = ? WHERE singleton_key = 1",
                    (
                        target.schema_version,
                        target.source_revision,
                        target.source_migration_count,
                        sqlite_schema_digest(connection),
                        encode_utc_timestamp(datetime.now(UTC)),
                    ),
                )
    except SqliteCanonicalUpgradeError:
        raise
    except SqliteMigrationDeltaError as exc:
        raise SqliteCanonicalUpgradeError(str(exc)) from exc
    except Exception as exc:
        raise SqliteCanonicalUpgradeError("sqlite_migration_step_failed") from exc
    finally:
        engine.dispose()


def _backup_database(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro",
        uri=True,
    )
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    except sqlite3.DatabaseError as exc:
        raise SqliteCanonicalUpgradeError("sqlite_backup_failed") from exc
    finally:
        target_connection.close()
        source_connection.close()


def _connection_identity(
    connection: object,
    *,
    excluded_tables: set[str] | None = None,
) -> dict[str, _TableIdentity]:
    excluded = excluded_tables or set()
    execute = getattr(connection, "exec_driver_sql")
    tables = [
        str(row[0])
        for row in execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name != ? ORDER BY name",
            (SCHEMA_VERSION_TABLE,),
        )
        if str(row[0]) not in excluded
    ]
    result: dict[str, _TableIdentity] = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        table_info = list(execute(f"PRAGMA table_info({quoted})"))
        columns = [str(row[1]) for row in table_info]
        primary_keys = [
            str(row[1])
            for row in sorted(table_info, key=lambda item: int(item[5]))
            if int(row[5]) > 0
        ]
        select_columns = ",".join(
            '"' + column.replace('"', '""') + '"' for column in columns
        )
        order_columns = primary_keys or columns
        order_by = ",".join(
            '"' + column.replace('"', '""') + '"'
            for column in order_columns
        )
        digest = hashlib.sha256()
        digest.update(repr(tuple(columns)).encode("utf-8"))
        digest.update(b"\n")
        row_count = 0
        for row in execute(
            f"SELECT {select_columns} FROM {quoted} ORDER BY {order_by}"
        ):
            row_count += 1
            digest.update(repr(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
        result[table] = _TableIdentity(row_count, digest.hexdigest())
    return result


def _database_file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    wal = path.with_name(path.name + "-wal")
    if wal.is_file():
        with wal.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _require_staging_capacity(source: Path, root: Path) -> None:
    required = max(source.stat().st_size * 2, 16 * 1024 * 1024)
    if shutil.disk_usage(root.parent).free < required:
        raise SqliteCanonicalUpgradeError("sqlite_migration_disk_space_low")


def _target_generation_name(source: str, version: int) -> str:
    suffix = f"-v{version}"
    if source.endswith("-v1"):
        value = source[:-3] + suffix
    else:
        value = source + f"-schema-v{version}"
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    value = "".join(
        character if character in allowed else "-" for character in value
    )
    return value[:64]


__all__ = [
    "SqliteCanonicalUpgradeCoordinator",
    "SqliteCanonicalUpgradeError",
    "SqliteCanonicalUpgradeResult",
]
