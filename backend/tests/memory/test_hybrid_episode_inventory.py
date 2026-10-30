"""The successor checks live sources without rewriting historical contracts."""

import importlib.util
from pathlib import Path

import pytest


def generator():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "hybrid_inventory_test", root / "scripts/ci/generate_hybrid_episode_memory_inventory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_inventory_preserves_predecessor_and_runtime_contract():
    module = generator()
    value = module.build_inventory()
    assert value["predecessor"]["sha256"] == module.PREDECESSOR_SHA256
    from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
    # The live successor follows the current schema; its frozen predecessor
    # attestation above stays unchanged when later additive migrations land.
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
    from app.runtime.persistence.postgresql_schema import VERSION as POSTGRESQL_SCHEMA_VERSION
    assert value["schema"]["postgresql_schema_version"] == POSTGRESQL_SCHEMA_VERSION
    assert value["schema"]["sqlite_input_schema_version"] == SQLITE_SCHEMA_VERSION
    assert value["contract"]["canonical_store"] == "postgresql"
    assert value["schema"]["schema_digest"] == manifest.schema_digest
    assert value["schema"]["canonical_table_count"] == manifest.canonical_table_count
    assert value["bounds"]["chat_new_turns"] == 50
    assert value["bounds"]["thought_characters"] == 280
    assert value["defaults"]["MEMORY_RECALL_REPRESENTATION"] == "episode_v1"
    paths = {item["path"] for item in value["files"]}
    assert "backend/app/runtime/contributor_backend.py" in paths
    assert "backend/app/domains/memory/repository/consolidation_requests.py" in paths


def test_successor_rejects_changed_predecessor(monkeypatch):
    module = generator()
    real = module.record
    monkeypatch.setattr(module, "record", lambda path: {
        **real(path), "sha256": "0" * 64} if path == module.ROOT / module.PREDECESSOR else real(path))
    with pytest.raises(ValueError, match="predecessor drift"):
        module.build_inventory()


def test_successor_rejects_stale_live_source_inventory(tmp_path, monkeypatch):
    module = generator()
    output = tmp_path / "inventory.json"
    output.write_text(module.render(), encoding="utf-8")
    monkeypatch.setattr(module, "OUTPUT", output)
    module.verify()
    real = module.build_inventory
    monkeypatch.setattr(module, "build_inventory", lambda: {**real(), "defaults": {}})
    with pytest.raises(ValueError, match="inventory drift"):
        module.verify()
