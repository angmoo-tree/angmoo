"""Production-OFF PostgreSQL to SQLite offline migration dry-run.

The adapter takes a repeatable, read-only source snapshot, copies every
canonical table into an owned temporary SQLite generation, verifies structural
and row parity, and only then publishes the completed dry-run generation.  It
never changes the application's configured canonical store.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import base64
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, MetaData, Table, inspect, select, text

from app.domains.runtime.ports.migration_source import MigrationSourcePort
from app.domains.runtime.ports.offline_migration import (
    OfflineMigrationManifest,
    OfflineMigrationReport,
    OfflineMigrationTableParity,
)
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import (
    EXPECTED_CANONICAL_TABLE_COUNT,
    SOURCE_ALEMBIC_MIGRATION_COUNT,
    SOURCE_ALEMBIC_REVISION,
    SQLITE_SCHEMA_VERSION,
    build_sqlite_baseline_metadata,
)


OFFLINE_MIGRATION_MANIFEST_VERSION = "angmoo-postgres-sqlite-dry-run-v1"
OFFLINE_MIGRATION_MANIFEST_NAME = "migration-manifest.json"
_COPY_BATCH_SIZE = 500


class OfflineMigrationError(RuntimeError):
    pass


class OfflineMigrationSourceError(OfflineMigrationError):
    pass


class OfflineMigrationTargetError(OfflineMigrationError):
    pass


class OfflineMigrationCancelledError(OfflineMigrationError):
    pass


class OfflineMigrationParityError(OfflineMigrationError):
    pass


class PostgresToSqliteOfflineDryRun:
    """Copy one immutable source snapshot into a verified SQLite generation."""

    def __init__(
        self,
        *,
        source_engine: Engine,
        source_metadata: MetaData,
        data_paths: RuntimeDataPathPort,
        migration_source: MigrationSourcePort,
        conversion_inventory_path: Path,
        generation: str,
        app_version: str,
        media_root: Path | None = None,
        media_manifest_path: Path | None = None,
        now: Callable[[], datetime] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        fault_injector: Callable[[str], None] | None = None,
        post_import_verifiers: Sequence[Callable[[Connection], None]] = (),
        allow_sqlite_source_for_tests: bool = False,
    ) -> None:
        self._source_engine = source_engine
        self._source_metadata = source_metadata
        self._data_paths = data_paths
        self._migration_source = migration_source
        self._conversion_inventory_path = conversion_inventory_path.resolve()
        self._generation = generation
        self._app_version = app_version
        self._media_root = media_root.resolve() if media_root is not None else None
        self._media_manifest_path = (
            media_manifest_path.resolve()
            if media_manifest_path is not None
            else None
        )
        self._now = now or (lambda: datetime.now(UTC))
        self._should_cancel = should_cancel or (lambda: False)
        self._fault_injector = fault_injector or (lambda _stage: None)
        self._post_import_verifiers = tuple(post_import_verifiers)
        self._allow_sqlite_source_for_tests = allow_sqlite_source_for_tests

    def dry_run(self) -> OfflineMigrationReport:
        paths = self._data_paths.resolve()
        generations_root = paths.canonical / "generations"
        final_directory = generations_root / self._generation
        temporary_generation = f"migration-tmp-{self._generation}"
        temporary_directory = generations_root / temporary_generation
        _assert_owned_generation_path(generations_root, final_directory)
        _assert_owned_generation_path(generations_root, temporary_directory)
        if final_directory.exists():
            raise OfflineMigrationTargetError(
                f"target generation already exists: {self._generation}"
            )
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)

        revisions, lineage_sha256, inventory_sha256 = self._validate_lineage()
        media_audit = self._audit_media_manifest()
        self._check_cancelled()
        self._fault_injector("before-source-snapshot")

        target_database = SqliteCanonicalDatabase(
            self._data_paths,
            settings=SqliteCanonicalSettings(generation=temporary_generation),
        )
        try:
            with self._source_engine.connect() as source_connection:
                source_transaction = source_connection.begin()
                try:
                    source_dialect = self._make_source_read_only(source_connection)
                    source_schema_sha256 = self._doctor_source(
                        source_connection,
                        expected_revision=revisions[-1],
                    )
                    target_doctor = target_database.open()
                    source_summaries = self._copy_snapshot(
                        source_connection,
                        target_database,
                    )
                    (
                        target_summaries,
                        foreign_key_violation_count,
                        integrity_check,
                    ) = self._verify_target(target_database)
                    if source_summaries != target_summaries:
                        raise OfflineMigrationParityError(
                            _describe_parity_mismatch(
                                source_summaries,
                                target_summaries,
                            )
                        )
                    self._fault_injector("before-manifest")
                    manifest = self._build_manifest(
                        source_dialect=source_dialect,
                        source_lineage_sha256=lineage_sha256,
                        source_schema_sha256=source_schema_sha256,
                        target_schema_sha256=target_doctor.schema_digest,
                        conversion_inventory_sha256=inventory_sha256,
                        media_audit=media_audit,
                        tables=source_summaries,
                    )
                    manifest_path = temporary_directory / OFFLINE_MIGRATION_MANIFEST_NAME
                    _write_manifest_atomic(manifest_path, manifest)
                    target_database.checkpoint(truncate=True)
                    target_database.close()
                    source_transaction.rollback()
                    self._fault_injector("before-publish")
                    temporary_directory.replace(final_directory)
                except Exception:
                    if source_transaction.is_active:
                        source_transaction.rollback()
                    raise
        except Exception:
            target_database.close()
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory)
            raise

        final_database_path = final_directory / "angmoo.sqlite3"
        final_manifest_path = final_directory / OFFLINE_MIGRATION_MANIFEST_NAME
        if not final_database_path.is_file() or not final_manifest_path.is_file():
            raise OfflineMigrationTargetError(
                "published migration generation is incomplete"
            )
        return OfflineMigrationReport(
            manifest=manifest,
            manifest_path=str(final_manifest_path),
            target_database_path=str(final_database_path),
            foreign_key_violation_count=foreign_key_violation_count,
            integrity_check=integrity_check,
            source_read_only=True,
            production_switched=False,
        )

    def _validate_lineage(self) -> tuple[tuple[str, ...], str, str]:
        if not self._conversion_inventory_path.is_file():
            raise OfflineMigrationSourceError("conversion inventory is missing")
        raw_inventory = self._conversion_inventory_path.read_bytes()
        try:
            inventory = json.loads(raw_inventory.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineMigrationSourceError(
                "conversion inventory is invalid"
            ) from exc
        revisions = self._migration_source.revisions()
        entries = inventory.get("entries")
        if not isinstance(entries, list):
            raise OfflineMigrationSourceError(
                "conversion inventory entries are missing"
            )
        if (
            inventory.get("migration_count") != SOURCE_ALEMBIC_MIGRATION_COUNT
            or len(entries) != SOURCE_ALEMBIC_MIGRATION_COUNT
            or len(revisions) != SOURCE_ALEMBIC_MIGRATION_COUNT
        ):
            raise OfflineMigrationSourceError("migration lineage count does not match")
        inventory_by_revision = {
            str(entry.get("revision")): entry
            for entry in entries
            if isinstance(entry, dict)
        }
        for revision in revisions:
            entry = inventory_by_revision.get(revision.revision)
            if entry is None:
                raise OfflineMigrationSourceError(
                    f"conversion inventory is missing revision {revision.revision}"
                )
            expected_path = f"backend/app/alembic/versions/{revision.path}"
            expected = (
                entry.get("path"),
                entry.get("down_revision"),
                entry.get("source_sha256"),
            )
            actual = (expected_path, revision.down_revision, revision.sha256)
            if expected != actual:
                raise OfflineMigrationSourceError(
                    f"conversion inventory drifted for revision {revision.revision}"
                )
        ordered = _order_revision_chain(revisions)
        if ordered[-1] != SOURCE_ALEMBIC_REVISION:
            raise OfflineMigrationSourceError("migration head revision does not match")
        lineage_payload = [
            {
                "revision": revision.revision,
                "down_revision": revision.down_revision,
                "path": revision.path,
                "sha256": revision.sha256,
            }
            for revision in revisions
        ]
        return (
            ordered,
            _sha256_json(lineage_payload),
            hashlib.sha256(raw_inventory).hexdigest(),
        )

    def _audit_media_manifest(self) -> str:
        if self._media_manifest_path is None:
            return "not_provided"
        if self._media_root is None:
            raise OfflineMigrationSourceError(
                "media_root is required when a media manifest is supplied"
            )
        if not self._media_manifest_path.is_file():
            raise OfflineMigrationSourceError("media manifest is missing")
        try:
            payload = json.loads(self._media_manifest_path.read_text("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineMigrationSourceError("media manifest is invalid") from exc
        files = payload.get("files")
        if payload.get("schema_version") != 1 or not isinstance(files, list):
            raise OfflineMigrationSourceError("media manifest schema is invalid")
        verified: list[dict[str, Any]] = []
        for entry in files:
            if not isinstance(entry, dict):
                raise OfflineMigrationSourceError("media manifest entry is invalid")
            relative = Path(str(entry.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise OfflineMigrationSourceError("media manifest path is unsafe")
            path = (self._media_root / relative).resolve()
            try:
                path.relative_to(self._media_root)
            except ValueError as exc:
                raise OfflineMigrationSourceError(
                    "media manifest path escapes the media root"
                ) from exc
            if not path.is_file():
                raise OfflineMigrationSourceError(
                    f"media file is missing: {relative.as_posix()}"
                )
            raw = path.read_bytes()
            expected_size = entry.get("size_bytes")
            expected_sha256 = entry.get("sha256")
            if expected_size != len(raw) or expected_sha256 != hashlib.sha256(raw).hexdigest():
                raise OfflineMigrationSourceError(
                    f"media file digest does not match: {relative.as_posix()}"
                )
            verified.append(
                {
                    "path": relative.as_posix(),
                    "size_bytes": len(raw),
                    "sha256": expected_sha256,
                }
            )
        return f"verified:{len(verified)}:{_sha256_json(verified)}"

    def _make_source_read_only(self, connection: Connection) -> str:
        dialect = connection.dialect.name
        if dialect == "postgresql":
            connection.execute(
                text(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
            )
            return dialect
        if dialect == "sqlite" and self._allow_sqlite_source_for_tests:
            connection.exec_driver_sql("PRAGMA query_only = ON")
            if int(connection.exec_driver_sql("PRAGMA query_only").scalar_one()) != 1:
                raise OfflineMigrationSourceError(
                    "synthetic SQLite source could not be made read-only"
                )
            return "sqlite-test-fixture"
        raise OfflineMigrationSourceError(
            f"offline migration source must be PostgreSQL, got {dialect}"
        )

    def _doctor_source(
        self,
        connection: Connection,
        *,
        expected_revision: str,
    ) -> str:
        inspector = inspect(connection)
        actual_tables = set(inspector.get_table_names())
        expected_tables = set(self._source_metadata.tables)
        missing_tables = sorted(expected_tables - actual_tables)
        if missing_tables:
            raise OfflineMigrationSourceError(
                "source canonical tables are missing: " + ", ".join(missing_tables)
            )
        if len(expected_tables) != EXPECTED_CANONICAL_TABLE_COUNT:
            raise OfflineMigrationSourceError(
                "source metadata canonical table count does not match"
            )
        if "alembic_version" not in actual_tables:
            raise OfflineMigrationSourceError("source Alembic version table is missing")
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        if revision != expected_revision:
            raise OfflineMigrationSourceError(
                f"source revision {revision!r} does not match {expected_revision!r}"
            )
        schema_rows: list[dict[str, Any]] = []
        for table_name in sorted(expected_tables):
            table = self._source_metadata.tables[table_name]
            actual_columns = {
                str(column["name"]): bool(column["nullable"])
                for column in inspector.get_columns(table_name)
            }
            expected_columns = {
                column.name: bool(column.nullable) for column in table.columns
            }
            if set(actual_columns) != set(expected_columns):
                raise OfflineMigrationSourceError(
                    f"source columns drifted for table {table_name}"
                )
            actual_pk = tuple(
                str(value)
                for value in inspector.get_pk_constraint(table_name).get(
                    "constrained_columns", ()
                )
            )
            expected_pk = tuple(column.name for column in table.primary_key.columns)
            if actual_pk != expected_pk:
                raise OfflineMigrationSourceError(
                    f"source primary key drifted for table {table_name}"
                )
            schema_rows.append(
                {
                    "table": table_name,
                    "columns": sorted(actual_columns),
                    "primary_key": list(actual_pk),
                }
            )
        return _sha256_json(schema_rows)

    def _copy_snapshot(
        self,
        source_connection: Connection,
        target_database: SqliteCanonicalDatabase,
    ) -> tuple[OfflineMigrationTableParity, ...]:
        target_metadata = build_sqlite_baseline_metadata()
        summaries: list[OfflineMigrationTableParity] = []
        with target_database.engine.connect() as target_connection:
            target_connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            target_connection.commit()
            transaction = target_connection.begin()
            try:
                for table_name in sorted(self._source_metadata.tables):
                    self._check_cancelled()
                    self._fault_injector(f"before-table:{table_name}")
                    source_table = self._source_metadata.tables[table_name]
                    target_table = target_metadata.tables[table_name]
                    summary = _copy_table(
                        source_connection,
                        target_connection,
                        source_table,
                        target_table,
                        should_cancel=self._should_cancel,
                    )
                    summaries.append(summary)
                    self._fault_injector(f"after-table:{table_name}")
                transaction.commit()
            except Exception:
                transaction.rollback()
                raise
            finally:
                target_connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                target_connection.commit()
        return tuple(summaries)

    def _verify_target(
        self,
        target_database: SqliteCanonicalDatabase,
    ) -> tuple[tuple[OfflineMigrationTableParity, ...], int, str]:
        target_metadata = build_sqlite_baseline_metadata()
        summaries: list[OfflineMigrationTableParity] = []
        with target_database.engine.connect() as connection:
            for table_name in sorted(target_metadata.tables):
                self._check_cancelled()
                summaries.append(
                    _summarize_table(connection, target_metadata.tables[table_name])
                )
            foreign_key_violations = list(
                connection.exec_driver_sql("PRAGMA foreign_key_check")
            )
            if foreign_key_violations:
                raise OfflineMigrationParityError(
                    "SQLite foreign_key_check reported "
                    f"{len(foreign_key_violations)} violation(s)"
                )
            integrity_check = str(
                connection.exec_driver_sql("PRAGMA integrity_check").scalar_one()
            )
            if integrity_check.lower() != "ok":
                raise OfflineMigrationParityError(
                    f"SQLite integrity_check failed: {integrity_check}"
                )
            for verifier in self._post_import_verifiers:
                verifier(connection)
        return tuple(summaries), 0, integrity_check

    def _build_manifest(
        self,
        *,
        source_dialect: str,
        source_lineage_sha256: str,
        source_schema_sha256: str,
        target_schema_sha256: str,
        conversion_inventory_sha256: str,
        media_audit: str,
        tables: tuple[OfflineMigrationTableParity, ...],
    ) -> OfflineMigrationManifest:
        created_at = self._now()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise OfflineMigrationError("manifest clock must be timezone-aware")
        created_at_text = created_at.astimezone(UTC).isoformat().replace(
            "+00:00", "Z"
        )
        content = {
            "manifest_version": OFFLINE_MIGRATION_MANIFEST_VERSION,
            "app_version": self._app_version,
            "source_revision": SOURCE_ALEMBIC_REVISION,
            "source_migration_count": SOURCE_ALEMBIC_MIGRATION_COUNT,
            "source_lineage_sha256": source_lineage_sha256,
            "source_schema_sha256": source_schema_sha256,
            "target_schema_version": SQLITE_SCHEMA_VERSION,
            "target_schema_sha256": target_schema_sha256,
            "conversion_inventory_sha256": conversion_inventory_sha256,
            "media_audit": media_audit,
            "tables": [asdict(table) for table in tables],
        }
        return OfflineMigrationManifest(
            manifest_version=OFFLINE_MIGRATION_MANIFEST_VERSION,
            app_version=self._app_version,
            created_at=created_at_text,
            source_dialect=source_dialect,
            source_revision=SOURCE_ALEMBIC_REVISION,
            source_migration_count=SOURCE_ALEMBIC_MIGRATION_COUNT,
            source_lineage_sha256=source_lineage_sha256,
            source_schema_sha256=source_schema_sha256,
            target_schema_version=SQLITE_SCHEMA_VERSION,
            target_schema_sha256=target_schema_sha256,
            conversion_inventory_sha256=conversion_inventory_sha256,
            media_audit=media_audit,
            tables=tables,
            content_sha256=_sha256_json(content),
        )

    def _check_cancelled(self) -> None:
        if self._should_cancel():
            raise OfflineMigrationCancelledError("offline migration was cancelled")


def _copy_table(
    source_connection: Connection,
    target_connection: Connection,
    source_table: Table,
    target_table: Table,
    *,
    should_cancel: Callable[[], bool],
) -> OfflineMigrationTableParity:
    primary_key_columns = tuple(column.name for column in source_table.primary_key.columns)
    statement = select(source_table).order_by(
        *(source_table.c[name] for name in primary_key_columns)
    )
    result = source_connection.execution_options(stream_results=True).execute(statement)
    row_hasher = hashlib.sha256()
    primary_key_hasher = hashlib.sha256()
    row_count = 0
    batch: list[dict[str, Any]] = []
    for row in result.mappings():
        if should_cancel():
            raise OfflineMigrationCancelledError("offline migration was cancelled")
        values = dict(row)
        _update_table_hashes(
            row_hasher,
            primary_key_hasher,
            values,
            primary_key_columns,
        )
        batch.append(_prepare_target_values(values))
        row_count += 1
        if len(batch) >= _COPY_BATCH_SIZE:
            target_connection.execute(target_table.insert(), batch)
            batch.clear()
    if batch:
        target_connection.execute(target_table.insert(), batch)
    return OfflineMigrationTableParity(
        table_name=source_table.name,
        primary_key_columns=primary_key_columns,
        row_count=row_count,
        primary_key_sha256=primary_key_hasher.hexdigest(),
        row_sha256=row_hasher.hexdigest(),
    )


def _summarize_table(
    connection: Connection,
    table: Table,
) -> OfflineMigrationTableParity:
    primary_key_columns = tuple(column.name for column in table.primary_key.columns)
    rows = connection.execute(
        select(table).order_by(*(table.c[name] for name in primary_key_columns))
    ).mappings()
    row_hasher = hashlib.sha256()
    primary_key_hasher = hashlib.sha256()
    row_count = 0
    for row in rows:
        values = dict(row)
        _update_table_hashes(
            row_hasher,
            primary_key_hasher,
            values,
            primary_key_columns,
        )
        row_count += 1
    return OfflineMigrationTableParity(
        table_name=table.name,
        primary_key_columns=primary_key_columns,
        row_count=row_count,
        primary_key_sha256=primary_key_hasher.hexdigest(),
        row_sha256=row_hasher.hexdigest(),
    )


def _update_table_hashes(
    row_hasher: Any,
    primary_key_hasher: Any,
    values: Mapping[str, Any],
    primary_key_columns: tuple[str, ...],
) -> None:
    canonical_row = {
        key: _canonical_value(value) for key, value in sorted(values.items())
    }
    canonical_primary_key = [canonical_row[name] for name in primary_key_columns]
    row_hasher.update(_canonical_json_bytes(canonical_row) + b"\n")
    primary_key_hasher.update(_canonical_json_bytes(canonical_primary_key) + b"\n")


def _prepare_target_values(values: Mapping[str, Any]) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    for key, value in values.items():
        if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
            value = value.tolist()
        prepared[key] = value
    return prepared


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value == 0:
            return 0.0
        return float(format(value, ".17g"))
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds") + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_canonical_value(item) for item in value]
    if hasattr(value, "tolist"):
        return _canonical_value(value.tolist())
    return str(value)


def _describe_parity_mismatch(
    source: tuple[OfflineMigrationTableParity, ...],
    target: tuple[OfflineMigrationTableParity, ...],
) -> str:
    source_by_table = {summary.table_name: summary for summary in source}
    target_by_table = {summary.table_name: summary for summary in target}
    mismatches = [
        table_name
        for table_name in sorted(set(source_by_table) | set(target_by_table))
        if source_by_table.get(table_name) != target_by_table.get(table_name)
    ]
    return "source/target row parity failed for: " + ", ".join(mismatches)


def _order_revision_chain(revisions: Sequence[Any]) -> tuple[str, ...]:
    by_parent = {revision.down_revision: revision.revision for revision in revisions}
    if len(by_parent) != len(revisions):
        raise OfflineMigrationSourceError("migration lineage branches are unsupported")
    ordered: list[str] = []
    parent: str | None = None
    while parent in by_parent:
        revision = by_parent[parent]
        ordered.append(revision)
        parent = revision
    if len(ordered) != len(revisions):
        raise OfflineMigrationSourceError("migration lineage is disconnected")
    return tuple(ordered)


def _write_manifest_atomic(
    path: Path,
    manifest: OfflineMigrationManifest,
) -> None:
    payload = asdict(manifest)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _assert_owned_generation_path(root: Path, candidate: Path) -> None:
    root = root.resolve()
    candidate = candidate.resolve()
    if candidate.parent != root or candidate == root:
        raise OfflineMigrationTargetError("migration generation path is not owned")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


__all__ = [
    "OFFLINE_MIGRATION_MANIFEST_NAME",
    "OFFLINE_MIGRATION_MANIFEST_VERSION",
    "OfflineMigrationCancelledError",
    "OfflineMigrationError",
    "OfflineMigrationParityError",
    "OfflineMigrationSourceError",
    "OfflineMigrationTargetError",
    "PostgresToSqliteOfflineDryRun",
]
