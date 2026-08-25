from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, MetaData, create_engine, select, text

from app import models  # noqa: F401 - registers the complete canonical metadata
from app.domains.runtime.ports.offline_migration import (
    OfflineCanonicalMigrationPort,
)
from app.runtime.migrations.alembic_source import AlembicMigrationSource
from app.runtime.migrations.postgres_to_sqlite import (
    OFFLINE_MIGRATION_MANIFEST_VERSION,
    OfflineMigrationCancelledError,
    OfflineMigrationSourceError,
    OfflineMigrationTargetError,
    PostgresToSqliteOfflineDryRun,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import (
    decode_json_document,
    encode_json_document,
)
from app.runtime.persistence.sqlite_schema import (
    EXPECTED_CANONICAL_TABLE_COUNT,
    SOURCE_ALEMBIC_MIGRATION_COUNT,
    SOURCE_ALEMBIC_REVISION,
    build_sqlite_baseline_metadata,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
VERSIONS_PATH = BACKEND_ROOT / "app" / "alembic" / "versions"
CONVERSION_INVENTORY = (
    REPOSITORY_ROOT / "docs" / "architecture" / "migration-conversion-inventory.json"
)
FIXED_NOW = datetime(2026, 8, 20, 3, 0, tzinfo=UTC)


def _source(tmp_path: Path) -> tuple[Engine, MetaData]:
    metadata = build_sqlite_baseline_metadata()
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'synthetic-postgres-source.sqlite3'}",
        json_serializer=encode_json_document,
        json_deserializer=decode_json_document,
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": SOURCE_ALEMBIC_REVISION},
        )
    return engine, metadata


def _dry_run(
    *,
    source_engine: Engine,
    source_metadata: MetaData,
    runtime_root: Path,
    generation: str,
    **kwargs: Any,
) -> PostgresToSqliteOfflineDryRun:
    return PostgresToSqliteOfflineDryRun(
        source_engine=source_engine,
        source_metadata=source_metadata,
        data_paths=StaticRuntimeDataPath(runtime_root),
        migration_source=AlembicMigrationSource(
            VERSIONS_PATH, head_revision=SOURCE_ALEMBIC_REVISION
        ),
        conversion_inventory_path=CONVERSION_INVENTORY,
        generation=generation,
        app_version="0.3.0",
        now=lambda: FIXED_NOW,
        allow_sqlite_source_for_tests=True,
        **kwargs,
    )


def _insert(connection: Any, metadata: MetaData, table: str, **values: Any) -> None:
    connection.execute(metadata.tables[table].insert().values(**values))


def _seed_l3_fixture(engine: Engine, metadata: MetaData) -> None:
    now = FIXED_NOW
    with engine.begin() as connection:
        _insert(
            connection,
            metadata,
            "users",
            id="owner",
            display_name="Local Owner",
            display_name_normalized="local owner",
            profile_setup_completed=True,
        )
        for world_id in ("world-a", "world-b"):
            _insert(
                connection,
                metadata,
                "worlds",
                id=world_id,
                slug=world_id,
                owner_user_id="owner",
                name=f"World {world_id[-1].upper()}",
                tagline="synthetic",
                setting_description="offline migration fixture",
                daily_life_description="deterministic routines",
                genre_tags=["fantasy"],
                tone_tags=["warm"],
                timezone="Asia/Seoul",
                language="ko",
                visibility="private",
                join_policy="private",
                status="published",
                definition_version=1,
                row_version=1,
                contract_version="world-v1",
                contract_hash="a" * 64,
                readiness_status="publish_ready",
                additional_generation_guidance="",
                create_idempotency_key=f"create-{world_id}",
                created_at=now,
                updated_at=now,
            )
            _insert(
                connection,
                metadata,
                "world_memberships",
                id=f"membership-{world_id}",
                world_id=world_id,
                user_id="owner",
                role="owner",
                status="active",
                joined_at=now,
                created_at=now,
                updated_at=now,
            )
        for character_id, name in (("mango", "망고"), ("sage", "세이지")):
            _insert(
                connection,
                metadata,
                "characters",
                id=character_id,
                owner_id="owner",
                name=name,
                handle=f"{character_id}-fixture",
                one_liner="synthetic character",
                personality="calm",
                speech_style="friendly",
                worldview="curious",
                topic_preferences="books",
                safety_rules="safe",
                status="active",
                moderation_status="active",
                execution_mode="llm",
                persona_summary=name,
                created_at=now,
            )
        for world_id in ("world-a", "world-b"):
            for character_id in ("mango", "sage"):
                _insert(
                    connection,
                    metadata,
                    "world_characters",
                    id=f"{world_id}-{character_id}",
                    world_id=world_id,
                    character_id=character_id,
                    membership_id=f"membership-{world_id}",
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=False,
                    activity_runtime_mode="routine_resident_v1",
                    feed_runtime_mode="keyword_search_v1",
                    local_profile={"name": character_id, "world": world_id},
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
        _insert(
            connection,
            metadata,
            "llm_credentials",
            id="credential-live",
            owner_id="owner",
            character_id="mango",
            provider="gemini",
            purpose="agent",
            model="gemini-fixture",
            auth_profile_id="fixture-live",
            label="Live key",
            encrypted_api_key="local-v2:synthetic-ciphertext",
            key_fingerprint="abc123",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        _insert(
            connection,
            metadata,
            "llm_credentials",
            id="credential-deleted",
            owner_id="owner",
            character_id="sage",
            provider="openai",
            purpose="agent",
            model="fixture-model",
            auth_profile_id="fixture-deleted",
            label="Deleted key",
            encrypted_api_key=None,
            key_fingerprint=None,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
        for suffix, world_id, hidden, deleted in (
            ("visible", "world-a", None, None),
            ("hidden", "world-a", now, None),
            ("deleted", "world-b", None, now),
        ):
            _insert(
                connection,
                metadata,
                "posts",
                id=f"post-{suffix}",
                author_character_id="mango",
                world_id=world_id,
                author_world_character_id=f"{world_id}-mango",
                post_type="post",
                visibility="public",
                author_name="망고",
                title=suffix,
                body="같은 문구이지만 World가 다릅니다.",
                search_document="같은 문구 World 격리",
                created_at=now,
                updated_at=now,
                report_count=1 if hidden else 0,
                report_hidden_at=hidden,
                deleted_at=deleted,
            )
        for suffix, world_id, target in (
            ("a", "world-a", "world-a-sage"),
            ("b", "world-b", "world-b-sage"),
        ):
            _insert(
                connection,
                metadata,
                "social_events",
                id=f"event-{suffix}",
                world_id=world_id,
                actor_world_character_id=f"{world_id}-mango",
                target_world_character_id=target,
                event_type="reply_created",
                result="succeeded",
                occurred_at=now,
                idempotency_key=f"event-{suffix}-key",
                schema_version="social-event-v1",
                retrieval_status="eligible",
                created_at=now,
            )
            _insert(
                connection,
                metadata,
                "relationship_states",
                id=f"relationship-{suffix}",
                world_id=world_id,
                actor_world_character_id=f"{world_id}-mango",
                target_world_character_id=target,
                familiarity=1,
                affinity=1,
                trust=1,
                tension=0,
                interaction_count=1,
                last_event_id=f"event-{suffix}",
                last_event_at=now,
                version=1,
                created_at=now,
                updated_at=now,
            )
        for suffix, status in (("pending", "pending"), ("failed", "dead")):
            event_suffix = "a" if suffix == "pending" else "b"
            world_id = "world-a" if suffix == "pending" else "world-b"
            _insert(
                connection,
                metadata,
                "graph_projection_outbox",
                id=f"outbox-{suffix}",
                world_id=world_id,
                source_event_id=f"event-{event_suffix}",
                projection_type="social_event",
                payload_version="relationship-v1",
                payload={"event_id": f"event-{event_suffix}"},
                source_signature=suffix[0] * 64,
                dedupe_key=f"outbox-{suffix}-key",
                status=status,
                attempt_count=0 if status == "pending" else 5,
                last_error_class=None if status == "pending" else "SyntheticError",
                created_at=now,
                updated_at=now,
            )


def test_empty_offline_dry_run_freezes_all_tables_and_lineage(tmp_path: Path) -> None:
    source_engine, metadata = _source(tmp_path)
    migration = _dry_run(
        source_engine=source_engine,
        source_metadata=metadata,
        runtime_root=tmp_path / "runtime",
        generation="empty",
    )

    assert isinstance(migration, OfflineCanonicalMigrationPort)
    report = migration.dry_run()

    assert report.manifest.manifest_version == OFFLINE_MIGRATION_MANIFEST_VERSION
    assert report.manifest.source_revision == SOURCE_ALEMBIC_REVISION
    assert report.manifest.source_migration_count == SOURCE_ALEMBIC_MIGRATION_COUNT
    assert len(report.manifest.tables) == EXPECTED_CANONICAL_TABLE_COUNT
    assert all(table.row_count == 0 for table in report.manifest.tables)
    assert report.source_read_only is True
    assert report.production_switched is False
    assert report.foreign_key_violation_count == 0
    assert report.integrity_check == "ok"
    assert Path(report.manifest_path).is_file()
    assert Path(report.target_database_path).is_file()
    source_engine.dispose()


def test_l3_synthetic_fixture_preserves_world_scope_outbox_and_credentials(
    tmp_path: Path,
) -> None:
    source_engine, metadata = _source(tmp_path)
    _seed_l3_fixture(source_engine, metadata)

    def verify_contract(connection: Any) -> None:
        assert connection.execute(text("SELECT count(*) FROM worlds")).scalar_one() == 2
        assert (
            connection.execute(text("SELECT count(*) FROM world_characters")).scalar_one()
            == 4
        )
        assert connection.execute(
            text(
                "SELECT count(DISTINCT world_id) FROM relationship_states "
                "WHERE actor_world_character_id LIKE '%-mango'"
            )
        ).scalar_one() == 2
        assert set(
            connection.execute(
                text("SELECT status FROM graph_projection_outbox")
            ).scalars()
        ) == {"pending", "dead"}
        assert connection.execute(
            text("SELECT count(*) FROM posts WHERE report_hidden_at IS NOT NULL")
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT count(*) FROM posts WHERE deleted_at IS NOT NULL")
        ).scalar_one() == 1

    report = _dry_run(
        source_engine=source_engine,
        source_metadata=metadata,
        runtime_root=tmp_path / "runtime",
        generation="l3-oracle",
        post_import_verifiers=(verify_contract,),
    ).dry_run()

    summaries = {table.table_name: table for table in report.manifest.tables}
    assert summaries["worlds"].row_count == 2
    assert summaries["world_characters"].row_count == 4
    assert summaries["graph_projection_outbox"].row_count == 2
    assert summaries["llm_credentials"].row_count == 2
    target = create_engine(f"sqlite+pysqlite:///{report.target_database_path}")
    with target.connect() as connection:
        credentials = connection.execute(
            text(
                "SELECT id, encrypted_api_key, enabled FROM llm_credentials "
                "ORDER BY id"
            )
        ).mappings().all()
    assert credentials[0]["id"] == "credential-deleted"
    assert credentials[0]["encrypted_api_key"] is None
    assert credentials[1]["encrypted_api_key"] == "local-v2:synthetic-ciphertext"
    target.dispose()
    source_engine.dispose()


def test_media_manifest_is_verified_and_missing_or_corrupt_data_fails_closed(
    tmp_path: Path,
) -> None:
    source_engine, metadata = _source(tmp_path)
    media_root = tmp_path / "media"
    media_file = media_root / "worlds" / "world-a" / "banner.png"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"synthetic-png")
    manifest_path = tmp_path / "media-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "worlds/world-a/banner.png",
                        "size_bytes": len(b"synthetic-png"),
                        "sha256": hashlib.sha256(b"synthetic-png").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    verified = _dry_run(
        source_engine=source_engine,
        source_metadata=metadata,
        runtime_root=tmp_path / "verified-runtime",
        generation="media-ok",
        media_root=media_root,
        media_manifest_path=manifest_path,
    ).dry_run()
    assert verified.manifest.media_audit.startswith("verified:1:")

    media_file.write_bytes(b"corrupt")
    with pytest.raises(OfflineMigrationSourceError, match="digest does not match"):
        _dry_run(
            source_engine=source_engine,
            source_metadata=metadata,
            runtime_root=tmp_path / "corrupt-runtime",
            generation="media-corrupt",
            media_root=media_root,
            media_manifest_path=manifest_path,
        ).dry_run()
    with pytest.raises(OfflineMigrationSourceError, match="manifest is missing"):
        _dry_run(
            source_engine=source_engine,
            source_metadata=metadata,
            runtime_root=tmp_path / "missing-runtime",
            generation="media-missing",
            media_root=media_root,
            media_manifest_path=tmp_path / "missing.json",
        ).dry_run()
    source_engine.dispose()


def test_cancel_and_disk_full_remove_only_owned_temp_and_rerun_succeeds(
    tmp_path: Path,
) -> None:
    source_engine, metadata = _source(tmp_path)
    _seed_l3_fixture(source_engine, metadata)
    runtime_root = tmp_path / "runtime"
    checks = 0

    def cancel_after_copy_starts() -> bool:
        nonlocal checks
        checks += 1
        return checks > 12

    with pytest.raises(OfflineMigrationCancelledError):
        _dry_run(
            source_engine=source_engine,
            source_metadata=metadata,
            runtime_root=runtime_root,
            generation="cancelled",
            should_cancel=cancel_after_copy_starts,
        ).dry_run()
    assert not (
        runtime_root / "canonical" / "generations" / "migration-tmp-cancelled"
    ).exists()
    assert not (runtime_root / "canonical" / "generations" / "cancelled").exists()

    def disk_full(stage: str) -> None:
        if stage == "after-table:users":
            raise OSError("synthetic disk full")

    with pytest.raises(OSError, match="disk full"):
        _dry_run(
            source_engine=source_engine,
            source_metadata=metadata,
            runtime_root=runtime_root,
            generation="retry",
            fault_injector=disk_full,
        ).dry_run()
    assert not (
        runtime_root / "canonical" / "generations" / "migration-tmp-retry"
    ).exists()

    recovered = _dry_run(
        source_engine=source_engine,
        source_metadata=metadata,
        runtime_root=runtime_root,
        generation="retry",
    ).dry_run()
    assert Path(recovered.target_database_path).is_file()
    with pytest.raises(OfflineMigrationTargetError, match="already exists"):
        _dry_run(
            source_engine=source_engine,
            source_metadata=metadata,
            runtime_root=runtime_root,
            generation="retry",
        ).dry_run()
    source_engine.dispose()


def test_bad_revision_and_non_postgresql_source_fail_before_target_creation(
    tmp_path: Path,
) -> None:
    source_engine, metadata = _source(tmp_path)
    with source_engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = 'stale-revision'")
        )
    with pytest.raises(OfflineMigrationSourceError, match="source revision"):
        _dry_run(
            source_engine=source_engine,
            source_metadata=metadata,
            runtime_root=tmp_path / "stale-runtime",
            generation="stale",
        ).dry_run()

    strict = PostgresToSqliteOfflineDryRun(
        source_engine=source_engine,
        source_metadata=metadata,
        data_paths=StaticRuntimeDataPath(tmp_path / "strict-runtime"),
        migration_source=AlembicMigrationSource(
            VERSIONS_PATH, head_revision=SOURCE_ALEMBIC_REVISION
        ),
        conversion_inventory_path=CONVERSION_INVENTORY,
        generation="strict",
        app_version="0.3.0",
    )
    with pytest.raises(OfflineMigrationSourceError, match="must be PostgreSQL"):
        strict.dry_run()
    source_engine.dispose()
