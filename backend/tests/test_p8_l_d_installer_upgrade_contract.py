from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
from types import ModuleType

import pytest
from sqlalchemy import URL, create_engine

from app.runtime.migrations.sqlite_versions.v3_to_v4_world_scoped_chat import (
    capture_v3_to_v4_delta,
    upgrade_v3_to_v4,
    verify_v3_to_v4_delta,
)


ROOT = Path(__file__).resolve().parents[2]


def _script_module(name: str, relative: str) -> ModuleType:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"script import failed: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("source_version", (1, 2, 3, 4))
def test_supported_installer_builder_freezes_every_readable_predecessor(
    tmp_path: Path,
    source_version: int,
) -> None:
    builder = _script_module(
        f"p8_l_d_supported_upgrade_builder_v{source_version}",
        "scripts/ci/build_windows_installer_supported_upgrade_fixture.py",
    )
    host = tmp_path / "host.exe"
    sidecar = tmp_path / "sidecar.exe"
    host.write_bytes(b"synthetic host")
    sidecar.write_bytes(b"synthetic sidecar")
    fixture_root = tmp_path / f"fixture-v{source_version}"

    builder.build_fixture(
        fixture_root,
        host=host,
        sidecar=sidecar,
        source_version=source_version,
        conflict=False,
    )

    fixture = json.loads(
        (fixture_root / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    database_path = (
        fixture_root
        / "canonical"
        / "generations"
        / fixture["generation"]
        / "angmoo.sqlite3"
    )
    source = sqlite3.connect(database_path)
    source.row_factory = sqlite3.Row
    try:
        assert (
            source.execute(
                "SELECT schema_version FROM angmoo_schema_version"
            ).fetchone()[0]
            == source_version
        )
        assert source.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert source.execute("PRAGMA foreign_key_check").fetchall() == []
        assert source.execute(
            "SELECT count(*) FROM message_threads"
        ).fetchone()[0] == 2
        assert source.execute(
            "SELECT count(*) FROM message_messages"
        ).fetchone()[0] == 2
        roleless_count = int(
            source.execute(
                "SELECT count(*) FROM world_characters "
                "WHERE control_mode = 'autonomous' AND role_key IS NULL"
            ).fetchone()[0]
        )
        reserved_roles = source.execute(
            "SELECT world_id, status, version FROM world_roles "
            "WHERE role_key = 'no_specific_role' ORDER BY world_id"
        ).fetchall()
        if source_version < 3:
            assert roleless_count == 4
            actual_reserved_roles = [
                (row["world_id"], row["status"], row["version"])
                for row in reserved_roles
            ]
            assert actual_reserved_roles == [
                ("world-supported-v2-existing-role", "disabled", 3)
            ]
        else:
            assert roleless_count == 0
            actual_reserved_roles = [
                (row["world_id"], row["status"], row["version"])
                for row in reserved_roles
            ]
            assert actual_reserved_roles == [
                ("world-supported-v2", "enabled", 1),
                ("world-supported-v2-existing-role", "enabled", 4),
                ("world-supported-v2-second", "enabled", 1),
            ]
    finally:
        source.close()
    assert fixture["target_data_version"] == 5
    assert fixture["target_table_count"] == 94


def test_v3_installer_fixture_is_legacy_shaped_and_proves_v4_chat_backfill(
    tmp_path: Path,
) -> None:
    builder = _script_module(
        "p8_l_d_supported_upgrade_builder",
        "scripts/ci/build_windows_installer_supported_upgrade_fixture.py",
    )
    verifier = _script_module(
        "p8_l_d_supported_upgrade_verifier",
        "scripts/ci/verify_windows_installer_supported_upgrade_fixture.py",
    )
    host = tmp_path / "host.exe"
    sidecar = tmp_path / "sidecar.exe"
    host.write_bytes(b"synthetic host")
    sidecar.write_bytes(b"synthetic sidecar")
    fixture_root = tmp_path / "fixture"

    builder.build_fixture(
        fixture_root,
        host=host,
        sidecar=sidecar,
        source_version=3,
        conflict=False,
    )

    fixture = json.loads(
        (fixture_root / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    database_path = (
        fixture_root
        / "canonical"
        / "generations"
        / fixture["generation"]
        / "angmoo.sqlite3"
    )
    source = sqlite3.connect(database_path)
    try:
        assert source.execute(
            "SELECT schema_version FROM angmoo_schema_version"
        ).fetchone() == (3,)
        columns = {
            row[1] for row in source.execute("PRAGMA table_info(message_threads)")
        }
        assert not {
            "world_id",
            "requester_world_character_id",
            "responding_world_character_id",
            "world_scope_status",
        }.intersection(columns)
        assert source.execute("SELECT count(*) FROM message_threads").fetchone() == (
            2,
        )
        assert source.execute("SELECT count(*) FROM message_messages").fetchone() == (
            2,
        )
    finally:
        source.close()

    engine = create_engine(URL.create("sqlite+pysqlite", database=str(database_path)))
    try:
        with engine.begin() as connection:
            snapshot = capture_v3_to_v4_delta(connection)
            upgrade_v3_to_v4(connection)
            verify_v3_to_v4_delta(connection, snapshot)
    finally:
        engine.dispose()

    upgraded = sqlite3.connect(database_path)
    upgraded.row_factory = sqlite3.Row
    try:
        verifier._verify_world_chat_identity(upgraded, fixture)
        upgraded.execute(
            "UPDATE message_messages SET content = 'drift' "
            "WHERE thread_id = 'thread-supported-world-resolved'"
        )
        upgraded.commit()
        with pytest.raises(
            SystemExit, match="supported_upgrade_world_chat_messages_changed"
        ):
            verifier._verify_world_chat_identity(upgraded, fixture)
    finally:
        upgraded.close()
