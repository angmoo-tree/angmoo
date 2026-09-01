from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _verifier_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "ci"
        / "verify_windows_installer_supported_upgrade_fixture.py"
    )
    spec = importlib.util.spec_from_file_location(
        "windows_installer_supported_upgrade_verifier",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("supported_upgrade_verifier_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verifier_distinguishes_graph_rebuild_from_idempotent_reinstall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _verifier_module()
    data_root = tmp_path / "Angmoo"
    result_path = data_root / "runtime" / "installer-data-upgrade-result.json"
    result_path.parent.mkdir(parents=True)
    app_root = data_root / "app"
    app_root.mkdir()
    (app_root / "angmoo-desktop.exe").write_bytes(b"candidate")
    (data_root / "runtime" / "installer-transaction.json").write_text(
        json.dumps({"phase": "complete"}),
        encoding="utf-8",
    )
    payload = {
        "build_commit": "a" * 40,
        "payload_generation": "b" * 64,
        "embedded_data": {"sqlite": {"target_version": 4}},
    }
    fixture = {
        "ladybug_source_data_version": 1,
        "app_host_sha256": "0" * 64,
        "target_data_version": 4,
    }

    monkeypatch.setattr(verifier, "_source_database", lambda *_: None)
    monkeypatch.setattr(verifier, "_verify_payload", lambda *_: payload)
    monkeypatch.setattr(verifier, "_verify_database", lambda *_: None)
    monkeypatch.setattr(verifier, "_verify_graph", lambda *_, **__: None)
    monkeypatch.setattr(verifier, "_verify_external_data", lambda *_: None)

    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "upgraded",
                "operation": "upgrade",
                "sqlite_source_version": 3,
                "sqlite_target_version": 4,
                "ladybug_source_version": 2,
                "ladybug_target_version": 2,
                "build_commit": payload["build_commit"],
                "payload_generation": payload["payload_generation"],
            }
        ),
        encoding="utf-8",
    )

    verifier.verify_upgraded(
        data_root,
        fixture,
        expected_source_version=3,
        expected_ladybug_source_version=2,
    )
    with pytest.raises(SystemExit, match="supported_upgrade_result_invalid"):
        verifier.verify_upgraded(
            data_root,
            fixture,
            expected_source_version=3,
            expected_ladybug_source_version=1,
        )


def test_graph_verifier_accepts_restored_and_rebuilt_lineage(
    tmp_path: Path,
) -> None:
    verifier = _verifier_module()
    data_root = tmp_path / "Angmoo"
    graph_root = data_root / "graph"
    source_relative = "generations/v1"
    source = graph_root / source_relative
    source.mkdir(parents=True)
    (source / "relationships.lbdb").write_bytes(b"v1")
    fixture = {
        "ladybug_source_data_version": 1,
        "graph_relative_path": source_relative,
    }
    (graph_root / "current-generation.json").write_text(
        json.dumps({"data_version": 1, "relative_path": source_relative}),
        encoding="utf-8",
    )

    verifier._verify_graph(
        data_root,
        fixture,
        expected_source_version=1,
        expected_version=1,
        expect_rebuild=False,
    )

    target_relative = "generations/v2"
    target = graph_root / target_relative
    target.mkdir(parents=True)
    (target / "relationships.lbdb").write_bytes(b"v2")
    (graph_root / "current-generation.json").write_text(
        json.dumps({"data_version": 2, "relative_path": target_relative}),
        encoding="utf-8",
    )
    (graph_root / "previous-generation.json").write_text(
        json.dumps({"data_version": 1, "relative_path": source_relative}),
        encoding="utf-8",
    )

    for expected_source_version in (1, 2):
        verifier._verify_graph(
            data_root,
            fixture,
            expected_source_version=expected_source_version,
            expected_version=2,
            expect_rebuild=True,
        )
