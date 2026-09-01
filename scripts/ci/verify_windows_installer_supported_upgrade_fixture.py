"""Verify the isolated supported-predecessor NSIS update and rollback cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


RESERVED_ROLE_KEY = "no_specific_role"
RESERVED_ROLE_NAME = "역할 없음"


def _fail(code: str) -> None:
    raise SystemExit(code)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("supported_upgrade_evidence_invalid") from exc
    if not isinstance(payload, dict):
        _fail("supported_upgrade_evidence_invalid")
    return payload


def _owned_generation(root: Path, marker: dict[str, Any]) -> Path:
    relative = Path(str(marker.get("relative_path") or ""))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("supported_upgrade_generation_marker_invalid")
    candidate = (root / relative).resolve()
    root = root.resolve()
    if candidate == root or root not in candidate.parents:
        _fail("supported_upgrade_generation_marker_invalid")
    return candidate


def _verify_payload(app_root: Path) -> dict[str, Any]:
    payload = _json(app_root / "installer-payload.json")
    files = payload.get("files")
    if not isinstance(files, dict):
        _fail("supported_upgrade_payload_invalid")
    for name in ("angmoo-desktop.exe", "angmoo-sidecar.exe"):
        expected = str(files.get(name) or "")
        path = app_root / name
        if len(expected) != 64 or not path.is_file() or _sha256(path) != expected:
            _fail("supported_upgrade_payload_digest_mismatch")
    return payload


def _source_database(data_root: Path, fixture: dict[str, Any]) -> Path:
    generation = str(fixture.get("generation") or "")
    path = (
        data_root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    if not path.is_file() or _sha256(path) != fixture.get("database_sha256"):
        _fail("supported_upgrade_source_generation_changed")
    return path


def _verify_external_data(data_root: Path, fixture: dict[str, Any]) -> None:
    for relative_key, digest_key, failure_code in (
        (
            "app_secret_relative_path",
            "app_secret_sha256",
            "supported_upgrade_app_secret_changed",
        ),
        (
            "media_relative_path",
            "media_sha256",
            "supported_upgrade_media_changed",
        ),
    ):
        relative = Path(str(fixture.get(relative_key) or ""))
        expected = str(fixture.get(digest_key) or "")
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or len(expected) != 64
        ):
            _fail("supported_upgrade_fixture_contract_invalid")
        path = (data_root / relative).resolve()
        root = data_root.resolve()
        if root not in path.parents or not path.is_file() or _sha256(path) != expected:
            _fail(failure_code)


def _verify_seed_identity(connection: sqlite3.Connection, fixture: dict[str, Any]) -> None:
    owner = fixture.get("expected_owner")
    world_ids = fixture.get("expected_world_ids")
    if not isinstance(owner, dict) or not isinstance(world_ids, list):
        _fail("supported_upgrade_fixture_contract_invalid")
    row = connection.execute(
        "SELECT id, email, display_name FROM users WHERE id = ?",
        (str(owner.get("id") or ""),),
    ).fetchone()
    if (
        row is None
        or row["email"] != owner.get("email")
        or row["display_name"] != owner.get("display_name")
    ):
        _fail("supported_upgrade_owner_changed")
    actual_world_ids = [
        str(item[0])
        for item in connection.execute(
            "SELECT id FROM worlds WHERE owner_user_id = ? ORDER BY id",
            (str(owner.get("id") or ""),),
        ).fetchall()
    ]
    if actual_world_ids != sorted(str(item) for item in world_ids):
        _fail("supported_upgrade_worlds_changed")


def _verify_world_chat_identity(
    connection: sqlite3.Connection, fixture: dict[str, Any]
) -> None:
    expected_threads = fixture.get("expected_world_chat_threads")
    if not isinstance(expected_threads, dict) or not expected_threads:
        _fail("supported_upgrade_fixture_contract_invalid")
    for thread_id, expected in sorted(expected_threads.items()):
        if not isinstance(expected, dict):
            _fail("supported_upgrade_fixture_contract_invalid")
        row = connection.execute(
            "SELECT requester_id, character_id, world_id, "
            "requester_world_character_id, responding_world_character_id, "
            "world_scope_status, selected_model "
            "FROM message_threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if row is None or any(
            row[key] != expected.get(key)
            for key in (
                "requester_id",
                "character_id",
                "world_id",
                "requester_world_character_id",
                "responding_world_character_id",
                "world_scope_status",
                "selected_model",
            )
        ):
            _fail("supported_upgrade_world_chat_identity_mismatch")
        messages = [
            {
                "role": item["role"],
                "content": item["content"],
                "model": item["model"],
                "status": item["status"],
            }
            for item in connection.execute(
                "SELECT role, content, model, status FROM message_messages "
                "WHERE thread_id = ? ORDER BY id",
                (thread_id,),
            ).fetchall()
        ]
        if messages != expected.get("messages"):
            _fail("supported_upgrade_world_chat_messages_changed")


def _verify_graph(
    data_root: Path,
    fixture: dict[str, Any],
    *,
    expected_source_version: int,
    expected_version: int,
    expect_rebuild: bool,
) -> None:
    graph_root = data_root / "graph"
    marker = _json(graph_root / "current-generation.json")
    source_version = int(fixture.get("ladybug_source_data_version", 0))
    source_relative = str(fixture.get("graph_relative_path") or "")
    if int(marker.get("data_version", 0)) != expected_version:
        _fail("supported_upgrade_graph_generation_changed")
    if expect_rebuild:
        if expected_source_version not in {source_version, expected_version}:
            _fail("supported_upgrade_graph_source_version_invalid")
        if marker.get("relative_path") == source_relative:
            _fail("supported_upgrade_graph_rebuild_missing")
        previous = _json(graph_root / "previous-generation.json")
        if (
            int(previous.get("data_version", 0)) != source_version
            or previous.get("relative_path") != source_relative
        ):
            _fail("supported_upgrade_graph_previous_version_mismatch")
    elif (
        expected_source_version != source_version
        or marker.get("relative_path") != source_relative
        or (graph_root / "previous-generation.json").exists()
    ):
        _fail("supported_upgrade_graph_generation_changed")
    generation = _owned_generation(graph_root, marker)
    if not (generation / "relationships.lbdb").is_file():
        _fail("supported_upgrade_graph_artifact_missing")


def _verify_database(data_root: Path, fixture: dict[str, Any]) -> None:
    source_version = int(fixture.get("source_data_version", 0))
    target_version = int(fixture.get("target_data_version", 0))
    target_table_count = int(fixture.get("target_table_count", 0))
    if target_version <= source_version or target_table_count <= 0:
        _fail("supported_upgrade_fixture_contract_invalid")
    canonical = data_root / "canonical"
    marker = _json(canonical / "current-generation.json")
    if int(marker.get("data_version", 0)) != target_version:
        _fail("supported_upgrade_target_version_mismatch")
    previous = _json(canonical / "previous-generation.json")
    if int(previous.get("data_version", 0)) != source_version:
        _fail("supported_upgrade_previous_version_mismatch")
    database = _owned_generation(canonical, marker) / "angmoo.sqlite3"
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            _fail("supported_upgrade_integrity_failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            _fail("supported_upgrade_foreign_key_failed")
        version = connection.execute(
            "SELECT schema_version FROM angmoo_schema_version "
            "WHERE singleton_key = 1"
        ).fetchone()
        if version is None or int(version[0]) != target_version:
            _fail("supported_upgrade_database_version_mismatch")
        table_count = int(
            connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' "
                "AND name != 'angmoo_schema_version'"
            ).fetchone()[0]
        )
        if table_count != target_table_count:
            _fail("supported_upgrade_table_count_mismatch")
        _verify_seed_identity(connection, fixture)
        _verify_world_chat_identity(connection, fixture)
        expected_roles = fixture.get("expected_reserved_roles")
        if not isinstance(expected_roles, dict):
            _fail("supported_upgrade_fixture_contract_invalid")
        for world_id, expected in expected_roles.items():
            if not isinstance(expected, dict):
                _fail("supported_upgrade_fixture_contract_invalid")
            roles = connection.execute(
                "SELECT id, role_key, name, status, version FROM world_roles "
                "WHERE world_id = ? AND role_key = ?",
                (world_id, RESERVED_ROLE_KEY),
            ).fetchall()
            if (
                len(roles) != 1
                or roles[0]["name"] != RESERVED_ROLE_NAME
                or roles[0]["status"] != "enabled"
                or int(roles[0]["version"]) != int(expected["version"])
                or (
                    expected.get("id") is not None
                    and roles[0]["id"] != expected["id"]
                )
            ):
                _fail("supported_upgrade_reserved_role_mismatch")
        worlds_without_reserved = fixture.get(
            "expected_worlds_without_reserved_role"
        )
        if not isinstance(worlds_without_reserved, list):
            _fail("supported_upgrade_fixture_contract_invalid")
        for world_id in worlds_without_reserved:
            count = int(
                connection.execute(
                    "SELECT count(*) FROM world_roles "
                    "WHERE world_id = ? AND role_key = ?",
                    (world_id, RESERVED_ROLE_KEY),
                ).fetchone()[0]
            )
            if count != 0:
                _fail("supported_upgrade_unnecessary_reserved_role")
        expected_characters = fixture.get("expected_world_character_roles")
        if not isinstance(expected_characters, dict):
            _fail("supported_upgrade_fixture_contract_invalid")
        for world_character_id, expected in expected_characters.items():
            if not isinstance(expected, dict):
                _fail("supported_upgrade_fixture_contract_invalid")
            row = connection.execute(
                "SELECT role_key, version FROM world_characters WHERE id = ?",
                (world_character_id,),
            ).fetchone()
            if (
                row is None
                or row["role_key"] != expected["role_key"]
                or int(row["version"]) != int(expected["version"])
            ):
                _fail("supported_upgrade_autonomous_role_mismatch")
        owner_controlled = connection.execute(
            "SELECT role_key, version, control_mode FROM world_characters "
            "WHERE id = ?",
            (fixture["expected_owner_controlled_world_character_id"],),
        ).fetchone()
        if (
            owner_controlled is None
            or owner_controlled["role_key"] is not None
            or int(owner_controlled["version"]) != 2
            or owner_controlled["control_mode"] != "owner_controlled"
        ):
            _fail("supported_upgrade_owner_controlled_changed")
        custom = connection.execute(
            "SELECT role_key, name, version FROM world_roles WHERE id = ?",
            ("custom-role-supported-v2",),
        ).fetchone()
        if (
            custom is None
            or custom["role_key"] != "harbor_guide"
            or custom["name"] != "Harbor Guide"
            or int(custom["version"]) != 1
        ):
            _fail("supported_upgrade_custom_role_changed")
        noop_custom = connection.execute(
            "SELECT role_key, name, version FROM world_roles WHERE id = ?",
            ("noop-custom-role-supported-v2",),
        ).fetchone()
        if (
            noop_custom is None
            or noop_custom["role_key"] != "archivist"
            or noop_custom["name"] != "Archivist"
            or int(noop_custom["version"]) != 1
        ):
            _fail("supported_upgrade_custom_role_changed")
        credential = connection.execute(
            "SELECT encrypted_api_key, key_fingerprint, enabled "
            "FROM llm_credentials WHERE id = ?",
            ("credential-supported-v2",),
        ).fetchone()
        if (
            credential is None
            or credential["encrypted_api_key"] != "synthetic-encrypted-value"
            or credential["key_fingerprint"] != "synthetic-fingerprint"
            or not bool(credential["enabled"])
        ):
            _fail("supported_upgrade_credential_changed")
    finally:
        connection.close()


def verify_upgraded(
    data_root: Path,
    fixture: dict[str, Any],
    *,
    expected_source_version: int,
    expected_ladybug_source_version: int,
) -> None:
    _source_database(data_root, fixture)
    target_version = int(fixture.get("target_data_version", 0))
    if target_version <= 0:
        _fail("supported_upgrade_fixture_contract_invalid")
    payload = _verify_payload(data_root / "app")
    sqlite_contract = payload.get("embedded_data", {}).get("sqlite", {})
    if int(sqlite_contract.get("target_version", 0)) != target_version:
        _fail("supported_upgrade_candidate_contract_invalid")
    if _sha256(data_root / "app" / "angmoo-desktop.exe") == fixture.get(
        "app_host_sha256"
    ):
        _fail("supported_upgrade_app_not_replaced")
    for path in (
        data_root / "app.__install_staging__",
        data_root / "app.__install_backup__",
    ):
        if path.exists():
            _fail("supported_upgrade_transaction_artifact_left")
    transaction = _json(data_root / "runtime" / "installer-transaction.json")
    if transaction.get("phase") != "complete":
        _fail("supported_upgrade_transaction_incomplete")
    result = _json(data_root / "runtime" / "installer-data-upgrade-result.json")
    if (
        int(result.get("schema_version", 0)) != 1
        or result.get("status") != "upgraded"
        or result.get("operation") != "upgrade"
        or int(result.get("sqlite_source_version", 0))
        != expected_source_version
        or int(result.get("sqlite_target_version", 0)) != target_version
        or int(result.get("ladybug_source_version", 0))
        != expected_ladybug_source_version
        or int(result.get("ladybug_target_version", 0)) != 2
        or result.get("build_commit") != payload.get("build_commit")
        or result.get("payload_generation") != payload.get("payload_generation")
    ):
        _fail("supported_upgrade_result_invalid")
    _verify_database(data_root, fixture)
    _verify_graph(
        data_root,
        fixture,
        expected_source_version=expected_ladybug_source_version,
        expected_version=2,
        expect_rebuild=True,
    )
    _verify_external_data(data_root, fixture)
    print("windows_installer_supported_upgrade_pass")


def verify_restored(data_root: Path, fixture: dict[str, Any]) -> None:
    source = _source_database(data_root, fixture)
    marker = _json(data_root / "canonical" / "current-generation.json")
    source_version = int(fixture.get("source_data_version", 0))
    target_version = int(fixture.get("target_data_version", 0))
    if int(marker.get("data_version", 0)) != source_version:
        _fail("supported_upgrade_failure_changed_active_generation")
    if (data_root / "canonical" / "previous-generation.json").exists():
        _fail("supported_upgrade_failure_created_previous_marker")
    payload = _verify_payload(data_root / "app")
    if payload.get("build_commit") != "1" * 40:
        _fail("supported_upgrade_previous_payload_not_restored")
    if _sha256(data_root / "app" / "angmoo-desktop.exe") != fixture.get(
        "app_host_sha256"
    ):
        _fail("supported_upgrade_previous_payload_not_restored")
    if _sha256(data_root / "app" / "angmoo-sidecar.exe") != fixture.get(
        "app_sidecar_sha256"
    ):
        _fail("supported_upgrade_previous_payload_not_restored")
    if _sha256(data_root / "app" / "uninstall.exe") != fixture.get(
        "app_uninstaller_sha256"
    ):
        _fail("supported_upgrade_previous_payload_not_restored")
    if _sha256(source) != fixture.get("database_sha256"):
        _fail("supported_upgrade_failure_changed_source")
    _verify_graph(
        data_root,
        fixture,
        expected_source_version=1,
        expected_version=1,
        expect_rebuild=False,
    )
    _verify_external_data(data_root, fixture)
    for path in (
        data_root / "app.__install_staging__",
        data_root / "app.__install_backup__",
    ):
        if path.exists():
            _fail("supported_upgrade_transaction_artifact_left")
    transaction = _json(data_root / "runtime" / "installer-transaction.json")
    if transaction.get("phase") != "failed_restored":
        _fail("supported_upgrade_restore_state_invalid")
    result = _json(data_root / "runtime" / "installer-data-upgrade-result.json")
    if (
        int(result.get("schema_version", 0)) != 1
        or result.get("status") != "failed"
        or result.get("operation") != "upgrade"
        or result.get("code") != "sqlite_migration_reserved_role_conflict"
        or int(result.get("sqlite_source_version", 0)) != source_version
        or int(result.get("sqlite_active_version", 0)) != source_version
        or int(result.get("sqlite_target_version", 0)) != target_version
        or int(result.get("ladybug_source_version", 0)) != 1
        or int(result.get("ladybug_active_version", 0)) != 1
        or int(result.get("ladybug_target_version", 0)) != 2
        or result.get("build_commit") == payload.get("build_commit")
        or len(str(result.get("build_commit") or "")) != 40
        or len(str(result.get("payload_generation") or "")) != 64
        or transaction.get("existing_payload")
        != "sqlite_migration_reserved_role_conflict"
    ):
        _fail("supported_upgrade_failure_result_invalid")
    print("windows_installer_failure_recovery_pass")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--fixture-manifest", type=Path, required=True)
    parser.add_argument(
        "--expected-status",
        choices=("upgraded", "restored"),
        required=True,
    )
    parser.add_argument("--expected-source-version", type=int)
    parser.add_argument("--expected-ladybug-source-version", type=int)
    args = parser.parse_args()
    root = args.data_root.resolve()
    fixture = _json(args.fixture_manifest.resolve())
    if not fixture.get("synthetic_fixture") or fixture.get(
        "contains_real_credentials"
    ):
        _fail("supported_upgrade_fixture_refused")
    if args.expected_status == "upgraded":
        if (
            args.expected_source_version is None
            or args.expected_ladybug_source_version is None
        ):
            _fail("supported_upgrade_expected_source_missing")
        verify_upgraded(
            root,
            fixture,
            expected_source_version=args.expected_source_version,
            expected_ladybug_source_version=(
                args.expected_ladybug_source_version
            ),
        )
    else:
        verify_restored(root, fixture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
