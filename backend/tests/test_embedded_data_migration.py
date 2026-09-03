from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.runtime.social.observations import observe_source
from app.domains.worlds.domain.reserved_roles import (
    NO_SPECIFIC_ROLE_DESCRIPTION,
    NO_SPECIFIC_ROLE_NAME,
)
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.integrations.relationship_graph_read import RelationshipGraphRepository
from app.runtime.migrations.embedded_data import EmbeddedDataUpgradeCoordinator
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeError
from app.domains.chat.infrastructure.world_scope_migration import (
    rebuild_message_threads_v3,
)
from app.domains.chat.infrastructure.sqlalchemy_models import (
    drop_response_request_schema,
)
from app.domains.memory.infrastructure.sqlalchemy_models import (
    drop_memory_schema_v1,
)
from app.domains.social.infrastructure.sqlalchemy_subjective_context_models import (
    drop_subjective_context_schema,
)
from app.runtime.migrations.ladybug_versions import registry as graph_registry
from app.runtime.migrations.local_app_data import LegacyLocalAppDataMigration
from app.runtime.migrations.sqlite_versions import registry as sqlite_registry
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    SQLITE_V1_SOURCE_ALEMBIC_MIGRATION_COUNT,
    SQLITE_V1_SOURCE_ALEMBIC_REVISION,
    SQLITE_SCHEMA_VERSION,
    WORLD_PACKAGE_REGISTRY_TABLES,
    build_sqlite_v1_metadata,
    create_schema_version_table,
    sqlite_schema_digest,
)
from p7_graph_support import seed_projection_fixture


GENERATION = "contributor-v1"
V2_GENERATION = "supported-v2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_v1(
    root: Path,
    *,
    with_graph: bool = True,
    generation: str = GENERATION,
) -> Path:
    secret = root / "secrets" / "app-secret"
    secret.parent.mkdir(parents=True)
    secret.write_text("embedded-migration-fixture-secret\n", encoding="utf-8")
    media = root / "media" / "world-a" / "banner.txt"
    media.parent.mkdir(parents=True)
    media.write_text("keep-media", encoding="utf-8")
    database = (
        root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    database.parent.mkdir(parents=True)
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(database)))
    metadata = build_sqlite_v1_metadata()
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        create_schema_version_table(connection)
        metadata.create_all(connection)
        raw_digest = sqlite_schema_digest(connection)
        connection.exec_driver_sql(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} ("
            "singleton_key, schema_version, source_revision, "
            "source_migration_count, schema_digest, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                1,
                1,
                SQLITE_V1_SOURCE_ALEMBIC_REVISION,
                SQLITE_V1_SOURCE_ALEMBIC_MIGRATION_COUNT,
                raw_digest,
                encode_utc_timestamp(datetime.now(UTC)),
            ),
        )
        connection.execute(
            metadata.tables["users"].insert().values(
                id="owner-v1",
                display_name="Existing Owner",
                display_name_normalized="existing owner",
                profile_setup_completed=True,
            )
        )
    engine.dispose()
    if with_graph:
        with LadybugRelationshipProjection(
            database_root=root / "graph" / "ladybug"
        ) as graph:
            graph.verify_connectivity()
    return database


def _seed_v2_roleless(
    root: Path,
    *,
    reserved_role_conflict: bool = False,
    canonical_reserved_role: bool = False,
    roleless_autonomous: bool = True,
    second_roleless_world: bool = False,
) -> Path:
    """Build a supported v2 predecessor with semantic rows that v3 changes."""

    secret = root / "secrets" / "app-secret"
    secret.parent.mkdir(parents=True)
    secret.write_text("supported-v2-secret\n", encoding="utf-8")
    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=V2_GENERATION),
    )
    database.open()
    old_world_hash = "b" * 64
    with database.session() as session:
        owner = models.User(
            id="owner-v2",
            email="owner-v2@example.test",
            display_name="Existing Owner",
            display_name_normalized="existing owner v2",
            privacy_policy_version="test",
            terms_version="test",
            profile_setup_completed=True,
        )
        world = models.World(
            id="world-v2",
            slug="supported-world-v2",
            owner_user_id=owner.id,
            name="Supported World",
            tagline="Existing data",
            setting_description="Existing setting",
            daily_life_description="Existing daily life",
            genre_tags=["fixture"],
            tone_tags=["stable"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="private",
            join_policy="private",
            status="published",
            contract_version="world-v1",
            contract_hash=old_world_hash,
            readiness_status="publish_ready",
            create_idempotency_key="supported-world-v2",
        )
        membership = models.WorldMembership(
            id="membership-v2",
            world_id=world.id,
            user_id=owner.id,
            role="owner",
            status="active",
            joined_at=datetime.now(UTC),
        )
        character_count = 4 if second_roleless_world else 3
        characters = [
            models.Character(
                id=f"character-v2-{index}",
                owner_id=owner.id,
                name=f"Character {index}",
                handle=f"supported-v2-{index}",
                one_liner="Existing character",
                personality="Careful",
                speech_style="Calm",
                worldview="Stable",
                topic_preferences="Migration",
                safety_rules="Safe",
                moderation_status="active",
                persona_summary="A supported predecessor character.",
            )
            for index in range(1, character_count + 1)
        ]
        session.add(owner)
        session.flush()
        session.add_all([world, *characters])
        session.flush()
        session.add(
            models.WorldRole(
                id="custom-role-v2",
                world_id=world.id,
                role_key="harbor_guide",
                name="Harbor Guide",
                description="A role that must remain unchanged.",
                responsibilities=["guide"],
                allowed_activity_scope=["harbor"],
                autonomous_allowed=True,
                status="enabled",
            )
        )
        if reserved_role_conflict:
            session.add(
                models.WorldRole(
                    id="conflicting-reserved-role-v2",
                    world_id=world.id,
                    role_key="no_specific_role",
                    name="Conflicting Name",
                    description="Not the canonical reserved role.",
                    responsibilities=["unexpected"],
                    allowed_activity_scope=[],
                    autonomous_allowed=True,
                    status="enabled",
                )
            )
        elif canonical_reserved_role:
            session.add(
                models.WorldRole(
                    id="canonical-reserved-role-v2",
                    world_id=world.id,
                    role_key="no_specific_role",
                    name=NO_SPECIFIC_ROLE_NAME,
                    description=NO_SPECIFIC_ROLE_DESCRIPTION,
                    responsibilities=[],
                    allowed_activity_scope=[],
                    autonomous_allowed=True,
                    status="enabled",
                    version=3,
                )
            )
        session.add(membership)
        session.flush()
        session.add_all(
            [
                models.WorldCharacter(
                    id="autonomous-v2-a",
                    world_id=world.id,
                    character_id=characters[0].id,
                    membership_id=membership.id,
                    role_key=(None if roleless_autonomous else "harbor_guide"),
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=True,
                    world_contract_hash=old_world_hash,
                    local_profile={"existing": True},
                    version=4,
                ),
                models.WorldCharacter(
                    id="autonomous-v2-b",
                    world_id=world.id,
                    character_id=characters[1].id,
                    membership_id=membership.id,
                    role_key=(None if roleless_autonomous else "harbor_guide"),
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=False,
                    world_contract_hash=old_world_hash,
                    local_profile={"existing": True},
                    version=7,
                ),
                models.WorldCharacter(
                    id="owner-controlled-v2",
                    world_id=world.id,
                    character_id=characters[2].id,
                    membership_id=membership.id,
                    role_key=None,
                    status="active",
                    control_mode="owner_controlled",
                    owner_user_id=owner.id,
                    autonomous_enabled=False,
                    world_contract_hash=old_world_hash,
                    local_profile={"existing": True},
                    version=2,
                ),
                models.LlmCredential(
                    id="credential-v2",
                    owner_id=owner.id,
                    character_id=characters[0].id,
                    provider="google",
                    purpose="agent",
                    model="fixture-model",
                    auth_profile_id="fixture-profile",
                    label="Existing credential",
                    encrypted_api_key="fixture-ciphertext",
                    key_fingerprint="fixture-fingerprint",
                    enabled=True,
                ),
            ]
        )
        if second_roleless_world:
            second_world = models.World(
                id="world-v2-second",
                slug="supported-world-v2-second",
                owner_user_id=owner.id,
                name="Second Supported World",
                tagline="Existing second world",
                setting_description="Another existing setting",
                daily_life_description="Another existing daily life",
                genre_tags=["fixture"],
                tone_tags=["stable"],
                timezone="Asia/Seoul",
                language="ko",
                visibility="private",
                join_policy="private",
                status="published",
                contract_version="world-v1",
                contract_hash="c" * 64,
                readiness_status="publish_ready",
                create_idempotency_key="supported-world-v2-second",
            )
            second_membership = models.WorldMembership(
                id="membership-v2-second",
                world_id=second_world.id,
                user_id=owner.id,
                role="owner",
                status="active",
                joined_at=datetime.now(UTC),
            )
            session.add(second_world)
            session.flush()
            session.add(second_membership)
            session.flush()
            session.add(
                models.WorldCharacter(
                    id="autonomous-v2-second-world",
                    world_id=second_world.id,
                    character_id=characters[3].id,
                    membership_id=second_membership.id,
                    role_key=None,
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=True,
                    world_contract_hash="c" * 64,
                    local_profile={"existing": True},
                    version=9,
                )
            )
        session.commit()
    database.checkpoint(truncate=True)
    path = database.database_path
    database.close()

    manifest = sqlite_registry.load_sqlite_manifest(2)
    predecessor_engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path))
    )
    try:
        with predecessor_engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                drop_subjective_context_schema(connection)
                drop_response_request_schema(connection)
                drop_memory_schema_v1(connection)
                rebuild_message_threads_v3(
                    connection, create_legacy_unique_index=False
                )
                connection.exec_driver_sql(
                    f"UPDATE {SCHEMA_VERSION_TABLE} "
                    "SET schema_version = ?, source_revision = ?, "
                    "source_migration_count = ?, schema_digest = ? "
                    "WHERE singleton_key = 1",
                    (
                        manifest.schema_version,
                        manifest.source_revision,
                        manifest.source_migration_count,
                        sqlite_schema_digest(connection),
                    ),
                )
    finally:
        predecessor_engine.dispose()
    return path


def test_legacy_marker_survives_forward_sqlite_generation_upgrade(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    legacy_generation = "er6-preview-v1"
    _seed_v1(source, generation=legacy_generation)

    legacy_migration = LegacyLocalAppDataMigration(
        source_root=source,
        target_root=target,
        runtime_root=target / "runtime",
        process_alive=lambda _pid: False,
    )
    imported = legacy_migration.migrate_if_needed()
    assert imported.status == "migrated"
    assert imported.generation == legacy_generation
    assert imported.schema_version == 1
    assert imported.canonical_table_count == 83

    upgraded = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(target),
        fallback_generation=legacy_generation,
    ).upgrade()
    assert upgraded.canonical.source_version == 1
    assert upgraded.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert upgraded.canonical.migrated is True
    assert upgraded.canonical.generation != legacy_generation

    # The ER6 marker attests the immutable v1 generation that was imported.
    # It must not reject a later active generation as marker corruption.
    completed = legacy_migration.migrate_if_needed()
    assert completed.status == "already_migrated"
    assert completed.generation == legacy_generation
    assert completed.schema_version == 1
    assert completed.canonical_table_count == 83


def test_v1_sqlite_is_copied_to_latest_and_existing_data_is_preserved(
    tmp_path: Path,
) -> None:
    root = tmp_path / "한글 contributor data"
    source = _seed_v1(root)
    source_sha = _sha256(source)
    secret_sha = _sha256(root / "secrets" / "app-secret")
    media_sha = _sha256(root / "media" / "world-a" / "banner.txt")

    first = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert first.canonical.source_version == 1
    assert first.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert first.canonical.migrated is True
    assert first.canonical.generation != GENERATION
    assert source.is_file()
    assert _sha256(source) == source_sha
    assert _sha256(root / "secrets" / "app-secret") == secret_sha
    assert _sha256(root / "media" / "world-a" / "banner.txt") == media_sha
    assert first.graph.rebuilt is False
    assert first.graph.degraded is False
    assert first.graph.database_root == (root / "graph" / "ladybug").resolve()

    connection = sqlite3.connect(first.canonical.database_path)
    try:
        version = connection.execute(
            f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE}"
        ).fetchone()[0]
        owner = connection.execute(
            "SELECT display_name FROM users WHERE id = 'owner-v1'"
        ).fetchone()[0]
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert version == SQLITE_SCHEMA_VERSION
    assert owner == "Existing Owner"
    assert set(WORLD_PACKAGE_REGISTRY_TABLES) <= tables

    previous = json.loads(
        (root / "canonical" / "previous-generation.json").read_text(
            encoding="utf-8"
        )
    )
    assert previous["generation"] == GENERATION
    assert previous["data_version"] == 1

    current_before = (
        root / "canonical" / "current-generation.json"
    ).read_bytes()
    graph_current_before = (
        root / "graph" / "current-generation.json"
    ).read_bytes()
    second = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()
    assert second.canonical.migrated is False
    assert second.canonical.database_path == first.canonical.database_path
    assert (
        root / "canonical" / "current-generation.json"
    ).read_bytes() == current_before
    assert second.graph.rebuilt is False
    assert (
        root / "graph" / "current-generation.json"
    ).read_bytes() == graph_current_before


def test_supported_v2_roleless_rows_are_promoted_by_exact_expected_delta(
    tmp_path: Path,
) -> None:
    root = tmp_path / "supported-v2"
    source = _seed_v2_roleless(root)
    source_sha = _sha256(source)
    secret_sha = _sha256(root / "secrets" / "app-secret")

    first = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=V2_GENERATION,
    ).upgrade()

    assert first.canonical.source_version == 2
    assert first.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert first.canonical.migrated is True
    assert first.canonical.generation != V2_GENERATION
    assert _sha256(source) == source_sha
    assert _sha256(root / "secrets" / "app-secret") == secret_sha

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=first.canonical.generation),
    )
    doctor = database.open()
    assert doctor.schema_version == SQLITE_SCHEMA_VERSION
    with database.session() as session:
        reserved_roles = list(
            session.scalars(
                select(models.WorldRole).where(
                    models.WorldRole.world_id == "world-v2",
                    models.WorldRole.role_key == "no_specific_role",
                )
            )
        )
        assert len(reserved_roles) == 1
        assert reserved_roles[0].name == "역할 없음"
        autonomous = {
            row.id: row
            for row in session.scalars(
                select(models.WorldCharacter).where(
                    models.WorldCharacter.id.in_(
                        ("autonomous-v2-a", "autonomous-v2-b")
                    )
                )
            )
        }
        assert autonomous["autonomous-v2-a"].role_key == "no_specific_role"
        assert autonomous["autonomous-v2-a"].version == 5
        assert autonomous["autonomous-v2-b"].role_key == "no_specific_role"
        assert autonomous["autonomous-v2-b"].version == 8
        owner_controlled = session.get(
            models.WorldCharacter,
            "owner-controlled-v2",
        )
        assert owner_controlled is not None
        assert owner_controlled.role_key is None
        assert owner_controlled.version == 2
        custom_role = session.get(models.WorldRole, "custom-role-v2")
        assert custom_role is not None
        assert custom_role.role_key == "harbor_guide"
        assert custom_role.version == 1
        credential = session.get(models.LlmCredential, "credential-v2")
        assert credential is not None
        assert credential.encrypted_api_key == "fixture-ciphertext"
        assert credential.key_fingerprint == "fixture-fingerprint"
    database.close()

    previous = json.loads(
        (root / "canonical" / "previous-generation.json").read_text(
            encoding="utf-8"
        )
    )
    assert previous["generation"] == V2_GENERATION
    assert previous["data_version"] == 2

    marker_before = (
        root / "canonical" / "current-generation.json"
    ).read_bytes()
    second = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=V2_GENERATION,
    ).upgrade()
    assert second.canonical.migrated is False
    assert second.canonical.database_path == first.canonical.database_path
    assert (
        root / "canonical" / "current-generation.json"
    ).read_bytes() == marker_before


def test_supported_v2_without_roleless_rows_adds_no_reserved_role(
    tmp_path: Path,
) -> None:
    root = tmp_path / "supported-v2-no-roleless"
    _seed_v2_roleless(root, roleless_autonomous=False)

    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=V2_GENERATION,
    ).upgrade()

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=result.canonical.generation),
    )
    database.open()
    with database.session() as session:
        reserved = list(
            session.scalars(
                select(models.WorldRole).where(
                    models.WorldRole.role_key == "no_specific_role"
                )
            )
        )
        assert reserved == []
        autonomous = list(
            session.scalars(
                select(models.WorldCharacter)
                .where(models.WorldCharacter.control_mode == "autonomous")
                .order_by(models.WorldCharacter.id)
            )
        )
        assert [(row.role_key, row.version) for row in autonomous] == [
            ("harbor_guide", 4),
            ("harbor_guide", 7),
        ]
    database.close()


def test_supported_v2_reuses_existing_canonical_reserved_role(
    tmp_path: Path,
) -> None:
    root = tmp_path / "supported-v2-existing-reserved"
    _seed_v2_roleless(root, canonical_reserved_role=True)

    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=V2_GENERATION,
    ).upgrade()

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=result.canonical.generation),
    )
    database.open()
    with database.session() as session:
        reserved = list(
            session.scalars(
                select(models.WorldRole).where(
                    models.WorldRole.world_id == "world-v2",
                    models.WorldRole.role_key == "no_specific_role",
                )
            )
        )
        assert len(reserved) == 1
        assert reserved[0].id == "canonical-reserved-role-v2"
        assert reserved[0].version == 3
    database.close()


def test_supported_v2_creates_one_reserved_role_per_affected_world(
    tmp_path: Path,
) -> None:
    root = tmp_path / "supported-v2-multiple-worlds"
    _seed_v2_roleless(root, second_roleless_world=True)

    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=V2_GENERATION,
    ).upgrade()

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=result.canonical.generation),
    )
    database.open()
    with database.session() as session:
        reserved = list(
            session.scalars(
                select(models.WorldRole)
                .where(models.WorldRole.role_key == "no_specific_role")
                .order_by(models.WorldRole.world_id)
            )
        )
        assert [row.world_id for row in reserved] == [
            "world-v2",
            "world-v2-second",
        ]
        second = session.get(
            models.WorldCharacter,
            "autonomous-v2-second-world",
        )
        assert second is not None
        assert second.role_key == "no_specific_role"
        assert second.version == 10
    database.close()


def test_supported_v2_reserved_role_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "supported-v2-conflict"
    source = _seed_v2_roleless(root, reserved_role_conflict=True)
    source_sha = _sha256(source)

    with pytest.raises(
        SqliteCanonicalUpgradeError,
        match="sqlite_migration_reserved_role_conflict",
    ):
        EmbeddedDataUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=V2_GENERATION,
        ).upgrade()

    assert _sha256(source) == source_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))


def test_failed_sqlite_step_keeps_v1_active_and_removes_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "failure"
    source = _seed_v1(root)
    source_sha = _sha256(source)

    def fail_step(_connection) -> None:
        raise RuntimeError("injected")

    monkeypatch.setitem(sqlite_registry.MIGRATIONS, 1, fail_step)
    with pytest.raises(SqliteCanonicalUpgradeError, match="step_failed"):
        EmbeddedDataUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=GENERATION,
        ).upgrade()

    assert _sha256(source) == source_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))


def test_each_consecutive_step_rejects_undeclared_identity_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "undeclared-step-delta"
    source = _seed_v1(root)
    source_sha = _sha256(source)
    original = sqlite_registry.MIGRATIONS[1]

    def mutate_unowned_table(connection) -> None:
        original(connection)
        connection.exec_driver_sql(
            "UPDATE users SET display_name = 'Unexpected change' "
            "WHERE id = 'owner-v1'"
        )

    monkeypatch.setitem(sqlite_registry.MIGRATIONS, 1, mutate_unowned_table)
    with pytest.raises(
        SqliteCanonicalUpgradeError,
        match="sqlite_migration_identity_changed",
    ):
        EmbeddedDataUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=GENERATION,
        ).upgrade()

    assert _sha256(source) == source_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))


def test_newer_sqlite_generation_fails_closed_without_replacement(
    tmp_path: Path,
) -> None:
    root = tmp_path / "newer-version"
    source = _seed_v1(root)
    source_sha = _sha256(source)
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            f"UPDATE {SCHEMA_VERSION_TABLE} SET schema_version = 99 "
            "WHERE singleton_key = 1"
        )
        connection.commit()
    finally:
        connection.close()
    newer_sha = _sha256(source)

    with pytest.raises(
        SqliteCanonicalUpgradeError,
        match="newer_than_runtime",
    ):
        EmbeddedDataUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=GENERATION,
        ).upgrade()

    assert source_sha != newer_sha
    assert _sha256(source) == newer_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))


def test_graph_version_change_replays_to_staging_and_preserves_previous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "graph-rebuild"
    _seed_v1(root)
    previous_graph = root / "graph" / "ladybug" / "relationships.lbdb"
    previous_sha = _sha256(previous_graph)
    monkeypatch.setattr(
        "app.runtime.migrations.ladybug_projection."
        "inspect_ladybug_projection_schema_version",
        lambda _root: 0,
    )

    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert result.graph.rebuilt is True
    assert result.graph.database_root != root / "graph" / "ladybug"
    assert _sha256(previous_graph) == previous_sha
    assert (result.graph.database_root / "relationships.lbdb").exists()
    current = json.loads(
        (root / "graph" / "current-generation.json").read_text(encoding="utf-8")
    )
    assert current["relative_path"].startswith("generations/ladybug-v2")
    previous = json.loads(
        (root / "graph" / "previous-generation.json").read_text(
            encoding="utf-8"
        )
    )
    assert previous["relative_path"] == "ladybug"
    assert previous["data_version"] == 0


def test_graph_rebuild_failure_degrades_without_replacing_previous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "graph-failure"
    _seed_v1(root)
    previous_graph = root / "graph" / "ladybug" / "relationships.lbdb"
    previous_sha = _sha256(previous_graph)
    monkeypatch.setattr(
        "app.runtime.migrations.ladybug_projection."
        "inspect_ladybug_projection_schema_version",
        lambda _root: 0,
    )

    def fail_rebuild(**_kwargs):
        raise graph_registry.LadybugVersionContractError(
            "ladybug_rebuild_injected"
        )

    monkeypatch.setitem(graph_registry.GRAPH_REBUILDS, 2, fail_rebuild)
    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert result.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert result.graph.degraded is True
    assert result.graph.error_code == "ladybug_rebuild_injected"
    assert _sha256(previous_graph) == previous_sha
    assert not (root / "graph" / "current-generation.json").exists()


def test_graph_rebuild_replays_direction_evidence_and_world_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "graph-parity"
    _seed_v1(root)
    initial = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(initial.canonical.database_path))
    )
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="embedded-upgrade")
        observed = observe_source(
            db,
            world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=fixture.reply_post.id,
            lane="routine",
            observed_at=datetime(2026, 8, 12, 1, 5, tzinfo=UTC),
        )
        db.commit()
        world_id = fixture.world.id
        actor_id = fixture.actor_world_character.id
        target_id = fixture.target_world_character.id
        event_id = fixture.event.id
        observation_relationship_id = observed.relationship_state_id
    previous_graph = initial.graph.database_root / "relationships.lbdb"
    previous_sha = _sha256(previous_graph)
    monkeypatch.setattr(
        "app.runtime.migrations.ladybug_projection."
        "inspect_ladybug_projection_schema_version",
        lambda _root: 0,
    )

    rebuilt = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert rebuilt.graph.rebuilt is True
    assert rebuilt.graph.degraded is False
    assert _sha256(previous_graph) == previous_sha
    with LadybugRelationshipProjection(
        database_root=rebuilt.graph.database_root
    ) as projection:
        repository = RelationshipGraphRepository(projection)
        direct = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        reverse = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=target_id,
            target_world_character_id=actor_id,
        )
        evidence = repository.list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        reverse_evidence = repository.list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=target_id,
            target_world_character_id=actor_id,
        )
        cross_world = repository.get_direct_relationship(
            world_id="another-world",
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
    engine.dispose()
    assert len(direct) == 1
    assert len(reverse) == 1
    assert reverse[0].relationship_state_id == observation_relationship_id
    assert [row.event_id for row in evidence] == [event_id]
    assert [row.event_id for row in reverse_evidence] == [event_id]
    assert cross_world == []
