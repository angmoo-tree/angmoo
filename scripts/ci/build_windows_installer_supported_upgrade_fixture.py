"""Build isolated supported LocalAppData fixtures for the real NSIS gate."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import gc
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import ladybug as lb
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import models
from app.domains.worlds.domain.reserved_roles import (
    NO_SPECIFIC_ROLE_DESCRIPTION,
    NO_SPECIFIC_ROLE_KEY,
    NO_SPECIFIC_ROLE_NAME,
)
from app.runtime.migrations.generation import EmbeddedGenerationController
from app.runtime.migrations.ladybug_projection import (
    LadybugProjectionUpgradeCoordinator,
)
from app.runtime.migrations.ladybug_versions.registry import (
    load_ladybug_manifest,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    sqlite_schema_contract_digest,
    sqlite_schema_digest,
)


SUPPORTED_SOURCE_VERSIONS = (1, 2)
PREDECESSOR_BUILD_COMMIT = "1" * 40
PREDECESSOR_OVERLAY = b"\nANGMOO_SYNTHETIC_SUPPORTED_PREDECESSOR_PAYLOAD\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_payload_manifest(
    app_root: Path,
    *,
    source_version: int,
) -> dict[str, object]:
    host_digest = _sha256(app_root / "angmoo-desktop.exe")
    sidecar_digest = _sha256(app_root / "angmoo-sidecar.exe")
    product_version = f"0.3.99-supported-v{source_version}-fixture"
    identity_source = "\n".join(
        (
            product_version,
            PREDECESSOR_BUILD_COMMIT,
            host_digest,
            sidecar_digest,
            f"sqlite:1-{source_version}->{source_version}",
            "ladybug:0-1->1",
        )
    )
    return {
        "schema_version": 2,
        "product_version": product_version,
        "build_commit": PREDECESSOR_BUILD_COMMIT,
        "payload_generation": hashlib.sha256(
            identity_source.encode("utf-8")
        ).hexdigest(),
        "embedded_data": {
            "sqlite": {
                "minimum_readable_version": 1,
                "maximum_readable_version": source_version,
                "target_version": source_version,
            },
            "ladybug": {
                "minimum_readable_version": 0,
                "maximum_readable_version": 1,
                "target_version": 1,
            },
        },
        "files": {
            "angmoo-desktop.exe": host_digest,
            "angmoo-sidecar.exe": sidecar_digest,
        },
    }


def _seed_supported_predecessor(
    root: Path,
    *,
    source_version: int,
    conflict: bool,
) -> tuple[Path, str, str]:
    generation = f"supported-v{source_version}"
    (root / "secrets").mkdir(parents=True, exist_ok=True)
    (root / "secrets" / "app-secret").write_text(
        "supported-upgrade-fixture-secret\n",
        encoding="utf-8",
    )
    media_path = root / "media" / "supported-upgrade-fixture.txt"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_text(
        "supported predecessor media must survive direct update\n",
        encoding="utf-8",
    )
    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(root),
        settings=SqliteCanonicalSettings(generation=generation),
    )
    database.open()
    old_world_hash = "b" * 64
    with database.session() as session:
        owner = models.User(
            id="owner-supported-v2",
            email="supported-v2@example.test",
            display_name="Supported Owner",
            display_name_normalized="supported owner",
            profile_setup_completed=True,
        )
        world = models.World(
            id="world-supported-v2",
            slug="supported-upgrade-world",
            owner_user_id=owner.id,
            name="Supported Upgrade World",
            tagline="Installer predecessor fixture",
            setting_description="A deterministic supported predecessor.",
            daily_life_description="Existing data must survive the update.",
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
            create_idempotency_key="supported-upgrade-world",
        )
        membership = models.WorldMembership(
            id="membership-supported-v2",
            world_id=world.id,
            user_id=owner.id,
            role="owner",
            status="active",
            joined_at=datetime.now(UTC),
        )
        characters = [
            models.Character(
                id=f"character-supported-v2-{index}",
                owner_id=owner.id,
                name=f"Fixture Character {index}",
                handle=f"supported-upgrade-{index}",
                one_liner="Existing character",
                personality="Careful",
                speech_style="Calm",
                worldview="Stable",
                topic_preferences="Migration",
                safety_rules="Safe",
                moderation_status="active",
                persona_summary="A supported predecessor fixture character.",
            )
            for index in range(1, 7)
        ]
        session.add(owner)
        session.flush()
        session.add_all([world, *characters])
        session.flush()
        session.add(
            models.WorldRole(
                id="custom-role-supported-v2",
                world_id=world.id,
                role_key="harbor_guide",
                name="Harbor Guide",
                description="Must remain unchanged.",
                responsibilities=["guide"],
                allowed_activity_scope=["harbor"],
                autonomous_allowed=True,
                status="enabled",
            )
        )
        if conflict:
            session.add(
                models.WorldRole(
                    id="conflicting-reserved-role-supported-v2",
                    world_id=world.id,
                    role_key="no_specific_role",
                    name="Conflicting Name",
                    description="Deliberately violates the reserved contract.",
                    responsibilities=["unexpected"],
                    allowed_activity_scope=[],
                    autonomous_allowed=True,
                    status="enabled",
                )
            )
        session.add(membership)
        session.flush()
        session.add_all(
            [
                models.WorldCharacter(
                    id="autonomous-supported-v2-a",
                    world_id=world.id,
                    character_id=characters[0].id,
                    membership_id=membership.id,
                    role_key=None,
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=True,
                    world_contract_hash=old_world_hash,
                    version=4,
                ),
                models.WorldCharacter(
                    id="autonomous-supported-v2-b",
                    world_id=world.id,
                    character_id=characters[1].id,
                    membership_id=membership.id,
                    role_key=None,
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=False,
                    world_contract_hash=old_world_hash,
                    version=7,
                ),
                models.WorldCharacter(
                    id="owner-controlled-supported-v2",
                    world_id=world.id,
                    character_id=characters[2].id,
                    membership_id=membership.id,
                    role_key=None,
                    status="active",
                    control_mode="owner_controlled",
                    owner_user_id=owner.id,
                    autonomous_enabled=False,
                    world_contract_hash=old_world_hash,
                    version=2,
                ),
                models.LlmCredential(
                    id="credential-supported-v2",
                    owner_id=owner.id,
                    character_id=characters[0].id,
                    provider="google",
                    purpose="agent",
                    model="fixture-model",
                    auth_profile_id="fixture-profile",
                    label="Existing credential metadata",
                    encrypted_api_key="synthetic-encrypted-value",
                    key_fingerprint="synthetic-fingerprint",
                    enabled=True,
                ),
            ]
        )

        # Freeze the remaining supported v2 semantic branches in the same
        # predecessor database used by the real NSIS update job.  This proves
        # that the installer does not merely handle the one-world roleless
        # example while unit tests cover the rest.
        second_world = models.World(
            id="world-supported-v2-second",
            slug="supported-upgrade-world-second",
            owner_user_id=owner.id,
            name="Second Supported Upgrade World",
            tagline="Multi-world predecessor branch",
            setting_description="A second deterministic predecessor World.",
            daily_life_description="Its roleless character must be normalized.",
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
            create_idempotency_key="supported-upgrade-world-second",
        )
        noop_world = models.World(
            id="world-supported-v2-noop",
            slug="supported-upgrade-world-noop",
            owner_user_id=owner.id,
            name="No-op Supported Upgrade World",
            tagline="No roleless predecessor branch",
            setting_description="Its custom role must remain unchanged.",
            daily_life_description="No reserved role should be created here.",
            genre_tags=["fixture"],
            tone_tags=["stable"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="private",
            join_policy="private",
            status="published",
            contract_version="world-v1",
            contract_hash="d" * 64,
            readiness_status="publish_ready",
            create_idempotency_key="supported-upgrade-world-noop",
        )
        existing_role_world = models.World(
            id="world-supported-v2-existing-role",
            slug="supported-upgrade-world-existing-role",
            owner_user_id=owner.id,
            name="Existing Reserved Role World",
            tagline="Canonical reserved role predecessor branch",
            setting_description="The reserved role already exists.",
            daily_life_description="It is enabled without duplication.",
            genre_tags=["fixture"],
            tone_tags=["stable"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="private",
            join_policy="private",
            status="published",
            contract_version="world-v1",
            contract_hash="e" * 64,
            readiness_status="publish_ready",
            create_idempotency_key="supported-upgrade-world-existing-role",
        )
        session.add_all([second_world, noop_world, existing_role_world])
        session.flush()
        memberships = [
            models.WorldMembership(
                id="membership-supported-v2-second",
                world_id=second_world.id,
                user_id=owner.id,
                role="owner",
                status="active",
                joined_at=datetime.now(UTC),
            ),
            models.WorldMembership(
                id="membership-supported-v2-noop",
                world_id=noop_world.id,
                user_id=owner.id,
                role="owner",
                status="active",
                joined_at=datetime.now(UTC),
            ),
            models.WorldMembership(
                id="membership-supported-v2-existing-role",
                world_id=existing_role_world.id,
                user_id=owner.id,
                role="owner",
                status="active",
                joined_at=datetime.now(UTC),
            ),
        ]
        session.add_all(memberships)
        session.flush()
        session.add_all(
            [
                models.WorldRole(
                    id="noop-custom-role-supported-v2",
                    world_id=noop_world.id,
                    role_key="archivist",
                    name="Archivist",
                    description="A no-op branch role that must not change.",
                    responsibilities=["archive"],
                    allowed_activity_scope=["library"],
                    autonomous_allowed=True,
                    status="enabled",
                ),
                models.WorldRole(
                    id="existing-reserved-role-supported-v2",
                    world_id=existing_role_world.id,
                    role_key=NO_SPECIFIC_ROLE_KEY,
                    name=NO_SPECIFIC_ROLE_NAME,
                    description=NO_SPECIFIC_ROLE_DESCRIPTION,
                    responsibilities=[],
                    allowed_activity_scope=[],
                    autonomous_allowed=True,
                    status="disabled",
                    version=3,
                ),
                models.WorldCharacter(
                    id="autonomous-supported-v2-second-world",
                    world_id=second_world.id,
                    character_id=characters[3].id,
                    membership_id=memberships[0].id,
                    role_key=None,
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=True,
                    world_contract_hash="c" * 64,
                    version=9,
                ),
                models.WorldCharacter(
                    id="autonomous-supported-v2-noop",
                    world_id=noop_world.id,
                    character_id=characters[4].id,
                    membership_id=memberships[1].id,
                    role_key="archivist",
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=True,
                    world_contract_hash="d" * 64,
                    version=6,
                ),
                models.WorldCharacter(
                    id="autonomous-supported-v2-existing-role",
                    world_id=existing_role_world.id,
                    character_id=characters[5].id,
                    membership_id=memberships[2].id,
                    role_key=None,
                    status="active",
                    control_mode="autonomous",
                    autonomous_enabled=True,
                    world_contract_hash="e" * 64,
                    version=11,
                ),
            ]
        )
        session.commit()
    database.checkpoint(truncate=True)
    graph = LadybugProjectionUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        session_factory=database.session_factory,
    ).upgrade()
    if graph.degraded or graph.target_version != 2:
        raise RuntimeError("supported_upgrade_fixture_graph_invalid")
    # The fixture represents the last supported installed predecessor. Build
    # with the current adapter, then freeze the empty graph at the immutable v1
    # contract so the candidate installer must prove the real v1 -> v2 replay.
    graph_database = lb.Database(str(graph.database_root / "relationships.lbdb"))
    graph_connection = lb.Connection(graph_database)
    graph_connection.execute(
        "MATCH (meta:ProjectionMeta {id: $id}) "
        "SET meta.schema_version = $schema_version",
        parameters={
            "id": "relationship_projection",
            "schema_version": 1,
        },
    )
    del graph_connection
    del graph_database
    gc.collect()
    graph_manifest = load_ladybug_manifest(1)
    _write_json(
        graph.database_root / "projection-manifest.json",
        graph_manifest.as_dict(),
    )
    graph_controller = EmbeddedGenerationController(
        root / "graph",
        artifact_relative_path="relationships.lbdb",
    )
    _write_json(
        graph_controller.current_marker,
        {
            "schema_version": 1,
            "relative_path": graph.database_root.relative_to(
                root / "graph"
            ).as_posix(),
            "manifest_sha256": graph_manifest.manifest_sha256,
            "data_version": 1,
        },
    )
    database_path = database.database_path
    database.close()

    manifest = load_sqlite_manifest(source_version)
    connection = sqlite3.connect(database_path)
    try:
        if source_version == 1:
            # v1 predates the four empty World Package registry tables. The
            # seeded domain data does not use those tables, so removing them
            # reconstructs the exact supported v1 schema without copying any
            # historical user database into the repository or CI artifact.
            connection.execute("PRAGMA foreign_keys = OFF")
            for table in (
                "world_package_import_id_maps",
                "world_package_imports",
                "world_package_exports",
                "world_package_sources",
            ):
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')
        connection.commit()
    finally:
        connection.close()

    engine = create_engine(URL.create("sqlite+pysqlite", database=str(database_path)))
    try:
        with engine.begin() as sql_connection:
            contract_digest = sqlite_schema_contract_digest(sql_connection)
            if contract_digest != manifest.schema_digest:
                raise RuntimeError("supported_upgrade_fixture_schema_contract_mismatch")
            sql_connection.exec_driver_sql(
                f"UPDATE {SCHEMA_VERSION_TABLE} "
                "SET schema_version = ?, source_revision = ?, "
                "source_migration_count = ?, schema_digest = ? "
                "WHERE singleton_key = 1",
                (
                    manifest.schema_version,
                    manifest.source_revision,
                    manifest.source_migration_count,
                    sqlite_schema_digest(sql_connection),
                ),
            )
    finally:
        engine.dispose()
    EmbeddedGenerationController(
        root / "canonical",
        artifact_relative_path="angmoo.sqlite3",
    ).promote(
        f"generations/{generation}",
        manifest_sha256=manifest.manifest_sha256,
        data_version=source_version,
    )
    graph_marker = json.loads(
        (root / "graph" / "current-generation.json").read_text(encoding="utf-8")
    )
    return database_path, generation, str(graph_marker["relative_path"])


def build_fixture(
    output_root: Path,
    *,
    host: Path,
    sidecar: Path,
    source_version: int,
    conflict: bool,
) -> None:
    if source_version not in SUPPORTED_SOURCE_VERSIONS:
        raise RuntimeError("supported_upgrade_fixture_source_unsupported")
    if conflict and source_version != 2:
        raise RuntimeError("supported_upgrade_fixture_conflict_source_invalid")
    if output_root.exists():
        raise RuntimeError("supported_upgrade_fixture_output_exists")
    output_root.mkdir(parents=True)
    app_root = output_root / "app"
    app_root.mkdir()
    shutil.copy2(host, app_root / "angmoo-desktop.exe")
    shutil.copy2(sidecar, app_root / "angmoo-sidecar.exe")
    shutil.copy2(host, app_root / "uninstall.exe")
    # A supported baseline payload must be distinguishable from the candidate
    # produced by this workflow. PE overlay bytes do not change the executable
    # image and let the existing payload verifier attest an immutable prior app
    # without storing historical binaries in Git.
    for executable in (
        "angmoo-desktop.exe",
        "angmoo-sidecar.exe",
        "uninstall.exe",
    ):
        with (app_root / executable).open("ab") as handle:
            handle.write(PREDECESSOR_OVERLAY)
    payload = _build_payload_manifest(
        app_root,
        source_version=source_version,
    )
    _write_json(app_root / "installer-payload.json", payload)
    database_path, generation, graph_relative_path = (
        _seed_supported_predecessor(
            output_root,
            source_version=source_version,
            conflict=conflict,
        )
    )
    _write_json(
        output_root / "fixture-manifest.json",
        {
            "schema_version": 1,
            "synthetic_fixture": True,
            "contains_real_credentials": False,
            "source_data_version": source_version,
            "target_data_version": 3,
            "ladybug_source_data_version": 1,
            "reserved_role_conflict": conflict,
            "generation": generation,
            "graph_relative_path": graph_relative_path,
            "database_sha256": _sha256(database_path),
            "app_secret_relative_path": "secrets/app-secret",
            "app_secret_sha256": _sha256(output_root / "secrets" / "app-secret"),
            "media_relative_path": "media/supported-upgrade-fixture.txt",
            "media_sha256": _sha256(
                output_root / "media" / "supported-upgrade-fixture.txt"
            ),
            "app_host_sha256": _sha256(app_root / "angmoo-desktop.exe"),
            "app_sidecar_sha256": _sha256(app_root / "angmoo-sidecar.exe"),
            "app_uninstaller_sha256": _sha256(app_root / "uninstall.exe"),
            "expected_owner": {
                "id": "owner-supported-v2",
                "email": "supported-v2@example.test",
                "display_name": "Supported Owner",
            },
            "expected_world_ids": [
                "world-supported-v2",
                "world-supported-v2-existing-role",
                "world-supported-v2-noop",
                "world-supported-v2-second",
            ],
            "expected_autonomous_world_character_ids": [
                "autonomous-supported-v2-a",
                "autonomous-supported-v2-b",
            ],
            "expected_world_character_roles": {
                "autonomous-supported-v2-a": {
                    "role_key": NO_SPECIFIC_ROLE_KEY,
                    "version": 5,
                },
                "autonomous-supported-v2-b": {
                    "role_key": NO_SPECIFIC_ROLE_KEY,
                    "version": 8,
                },
                "autonomous-supported-v2-second-world": {
                    "role_key": NO_SPECIFIC_ROLE_KEY,
                    "version": 10,
                },
                "autonomous-supported-v2-noop": {
                    "role_key": "archivist",
                    "version": 6,
                },
                "autonomous-supported-v2-existing-role": {
                    "role_key": NO_SPECIFIC_ROLE_KEY,
                    "version": 12,
                },
            },
            "expected_reserved_roles": {
                "world-supported-v2": {"version": 1},
                "world-supported-v2-second": {"version": 1},
                "world-supported-v2-existing-role": {
                    "id": "existing-reserved-role-supported-v2",
                    "version": 4,
                },
            },
            "expected_worlds_without_reserved_role": [
                "world-supported-v2-noop"
            ],
            "expected_owner_controlled_world_character_id": (
                "owner-controlled-supported-v2"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument(
        "--source-version",
        type=int,
        choices=SUPPORTED_SOURCE_VERSIONS,
        default=2,
    )
    parser.add_argument("--conflict", action="store_true")
    args = parser.parse_args()
    build_fixture(
        args.output_root.resolve(),
        host=args.host.resolve(),
        sidecar=args.sidecar.resolve(),
        source_version=args.source_version,
        conflict=args.conflict,
    )
    print(
        "windows_installer_supported_upgrade_fixture_ready:"
        f"{args.output_root.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
