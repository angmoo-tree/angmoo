from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from app.runtime.migrations import canonical_retention as retention
from app.runtime.migrations import embedded_sqlite as migration
from app.runtime.migrations.embedded_data import EmbeddedDataUpgradeCoordinator
from app.runtime.migrations.generation import EmbeddedGenerationController, EmbeddedGenerationError, EmbeddedUpgradeLock
from app.runtime.migrations.sqlite_versions import registry
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from test_embedded_data_migration import _seed_v1

pytestmark = pytest.mark.usefixtures("deny_external_network")


def clean(root):
    from app.runtime.contributor_backend import _register_canonical_models
    _register_canonical_models()
    paths = StaticRuntimeDataPath(root)
    result = EmbeddedDataUpgradeCoordinator(paths, fallback_generation="clean").upgrade()
    return result


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file() and path.suffix != ".lock"}


def new_copy(root, *, name, promote=True, confirmed=True):
    """A real SQLite backup and validation, not empty marker-only directories."""
    controller = EmbeddedGenerationController(root / "canonical", artifact_relative_path="angmoo.sqlite3")
    current = controller.current()
    relative = "generations/" + name
    source = root / "canonical" / current["relative_path"] / "angmoo.sqlite3"
    staging = controller.generations / ("." + name + ".tmp-fixture")
    staging.mkdir()
    retention.record_creation(staging, relative=relative, schema_version=current["data_version"],
        manifest_sha256=current["manifest_sha256"])
    migration._backup_database(source, staging / "angmoo.sqlite3")
    migration._validate_database(staging / "angmoo.sqlite3", registry.load_sqlite_manifest(current["data_version"]))
    retention.record_validated(staging)
    target = controller.finalize_staging(staging, relative)
    if promote:
        controller.promote(relative, manifest_sha256=current["manifest_sha256"], data_version=current["data_version"])
        migration._validate_database(target / "angmoo.sqlite3", registry.load_sqlite_manifest(current["data_version"]))
        if confirmed:
            retention.confirm_promotion(root, relative=relative, schema_version=current["data_version"],
                manifest_sha256=current["manifest_sha256"])
    return target


def prune(root, owner):
    with EmbeddedUpgradeLock(root / "runtime" / "embedded-data-migration.lock"):
        return retention.prune_generations(root, owner=owner)


def test_clean_creation_marked_but_existing_marker_recovery_is_not_backfilled(tmp_path):
    first = clean(tmp_path)
    ownership = first.canonical.database_path.parent / retention.OWNERSHIP_FILE
    assert retention._read(ownership, retention.GenerationOwnership).promotion_confirmed
    ownership.unlink()
    (tmp_path / "canonical" / "current-generation.json").unlink()
    before = first.canonical.database_path.read_bytes()
    repeated = clean(tmp_path)
    assert not ownership.exists() and not repeated.canonical.migrated
    assert repeated.canonical.database_path.read_bytes() == before


def test_real_historical_upgrade_chain_21_legacy_generations_and_ten_restarts(tmp_path, monkeypatch):
    source = _seed_v1(tmp_path, with_graph=False)
    legacy = [source.parent]
    for index in range(20):
        directory = source.parent.parent / f"legacy-{index}"
        directory.mkdir()
        migration._backup_database(source, directory / "angmoo.sqlite3")
        legacy.append(directory)
    hashes = {directory.name: hashlib.sha256((directory / "angmoo.sqlite3").read_bytes()).hexdigest() for directory in legacy}
    media_before = snapshot(tmp_path / "media")
    secret_before = snapshot(tmp_path / "secrets")
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    try:
        chain = registry.migration_chain
        for version in (23, 24, 25, 26):
            monkeypatch.setattr(migration, "SQLITE_SCHEMA_VERSION", version)
            monkeypatch.setattr(migration, "migration_chain", lambda source, version=version: chain(source, version))
            result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation=source.parent.name).upgrade(retention_owner=owner)
            assert result.canonical.target_version == version and result.canonical.migrated
        controller = EmbeddedGenerationController(tmp_path / "canonical", artifact_relative_path="angmoo.sqlite3")
        current, previous = controller.current(), json.loads(controller.previous_marker.read_text())
        managed = [p for p in controller.generations.iterdir() if (p / retention.OWNERSHIP_FILE).exists()]
        assert {p.relative_to(controller.root).as_posix() for p in managed} == {current["relative_path"], previous["relative_path"]}
        before = snapshot(tmp_path / "canonical")
        started = __import__("time").monotonic()
        for _ in range(10):
            result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation=source.parent.name).upgrade(retention_owner=owner)
            assert not result.canonical.migrated
        elapsed = __import__("time").monotonic() - started
        assert snapshot(tmp_path / "canonical") == before
        for directory in legacy:
            assert not (directory / retention.OWNERSHIP_FILE).exists()
            assert hashlib.sha256((directory / "angmoo.sqlite3").read_bytes()).hexdigest() == hashes[directory.name]
        assert snapshot(tmp_path / "media") == media_before and snapshot(tmp_path / "secrets") == secret_before
        with sqlite3.connect(result.canonical.database_path) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0
        (tmp_path / "generation-workload-metrics.json").write_text(json.dumps({
            "legacy_count": len(legacy), "managed_count": len(managed),
            "same_schema_restarts": 10, "restart_seconds": elapsed,
            "managed_bytes": sum((p / "angmoo.sqlite3").stat().st_size for p in managed),
            "legacy_bytes": sum((p / "angmoo.sqlite3").stat().st_size for p in legacy),
        }, indent=2))
    finally:
        owner.close()


def test_live_generation_pin_and_unconfirmed_staging_are_protected(tmp_path):
    first = clean(tmp_path)
    relative = "generations/" + first.canonical.generation
    pin = retention.GenerationUsePin(tmp_path, relative).acquire()
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    try:
        new_copy(tmp_path, name="B")
        new_copy(tmp_path, name="C")
        orphan = new_copy(tmp_path, name="unconfirmed", promote=False)
        staging = tmp_path / "canonical" / "generations" / ".unfinished.tmp-fixture"
        staging.mkdir(); (staging / "angmoo.sqlite3").write_bytes(b"unfinished")
        assert prune(tmp_path, owner).get("removed", 0) == 0
        assert first.canonical.database_path.exists() and orphan.exists() and staging.exists()
        pin.close()
        assert prune(tmp_path, owner)["removed"] == 1
        assert not first.canonical.database_path.parent.exists() and orphan.exists() and staging.exists()
    finally:
        pin.close(); owner.close()


@pytest.mark.parametrize("damage", ["unreadable_pin", "bad_previous", "unknown_marker_schema", "duplicate_markers",
    "unknown_file", "bad_ownership", "bad_digest", "path_traversal"])
def test_ambiguous_references_or_inventory_never_delete(tmp_path, damage):
    first = clean(tmp_path)
    new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    target = first.canonical.database_path.parent
    if damage == "unreadable_pin":
        pin = tmp_path / "runtime" / "canonical-uses" / "bad.json"
        pin.parent.mkdir(); pin.write_text("{")
    elif damage == "bad_previous":
        (tmp_path / "canonical" / "previous-generation.json").write_text("{")
    elif damage == "unknown_marker_schema":
        path = tmp_path / "canonical" / "previous-generation.json"
        payload = json.loads(path.read_text()); payload["data_version"] = 99999
        path.write_text(json.dumps(payload))
    elif damage == "duplicate_markers":
        (tmp_path / "canonical" / "previous-generation.json").write_bytes(
            (tmp_path / "canonical" / "current-generation.json").read_bytes())
    elif damage == "unknown_file":
        (target / "user-backup.txt").write_text("preserve")
    else:
        path = target / retention.OWNERSHIP_FILE
        payload = json.loads(path.read_text())
        if damage == "path_traversal": payload["relative_path"] = "../../outside"
        elif damage == "bad_digest": payload["manifest_sha256"] = "0" * 64
        else: payload["policy"] = "unknown"
        path.write_text(json.dumps(payload))
    before = first.canonical.database_path.read_bytes()
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    try:
        assert prune(tmp_path, owner).get("removed", 0) == 0
        assert first.canonical.database_path.read_bytes() == before
    finally:
        owner.close()


def test_partial_removal_intent_retries_without_new_copy_or_promotion(tmp_path, monkeypatch):
    first = clean(tmp_path)
    new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    target = first.canonical.database_path.parent
    original = Path.unlink
    def fail_ownership(path, *args, **kwargs):
        if path == target / retention.OWNERSHIP_FILE:
            raise OSError("injected partial removal")
        return original(path, *args, **kwargs)
    before_marker = (tmp_path / "canonical" / "current-generation.json").read_bytes()
    try:
        monkeypatch.setattr(Path, "unlink", fail_ownership)
        assert prune(tmp_path, owner)["deferred"] >= 1
        assert not first.canonical.database_path.exists() and target.exists()
        assert list((tmp_path / "runtime" / "canonical-removals").glob("*.json"))
        monkeypatch.setattr(Path, "unlink", original)
        result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="clean").upgrade(retention_owner=owner)
        assert not result.canonical.migrated and not target.exists()
        assert (tmp_path / "canonical" / "current-generation.json").read_bytes() == before_marker
        assert list((tmp_path / "runtime" / "canonical-removals").glob("*.json")) == []
    finally:
        owner.close()


def test_diagnostics_or_default_coordinator_never_delete_obsolete(tmp_path):
    first = clean(tmp_path)
    new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    before = snapshot(tmp_path / "canonical")
    result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="clean").upgrade()
    assert result.retention == {"unauthorized": 1} and first.canonical.database_path.exists()
    assert snapshot(tmp_path / "canonical") == before


def test_os_lock_excludes_other_serving_process_and_dead_pin_is_confirmed(tmp_path):
    first = clean(tmp_path)
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    source = "from pathlib import Path; from app.runtime.migrations.canonical_retention import ServingRetentionOwner; ServingRetentionOwner(Path(__import__('sys').argv[1])).acquire()"
    try:
        result = subprocess.run([sys.executable, "-c", source, str(tmp_path)], capture_output=True, text=True, timeout=30)
        assert result.returncode != 0 and "embedded_upgrade_locked" in result.stderr
    finally:
        owner.close()
    source = "from pathlib import Path; from app.runtime.migrations.canonical_retention import GenerationUsePin; p=GenerationUsePin(Path(__import__('sys').argv[1]),'generations/clean').acquire(); __import__('os')._exit(0)"
    assert subprocess.run([sys.executable, "-c", source, str(tmp_path)], timeout=30).returncode == 0
    assert list((tmp_path / "runtime" / "canonical-uses").glob("*.json"))
    new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    try:
        assert prune(tmp_path, owner)["removed"] == 1
        assert not first.canonical.database_path.exists()
        assert list((tmp_path / "runtime" / "canonical-uses").glob("*.json")) == []
    finally:
        owner.close()


def test_reparse_generation_is_refused_and_wal_lifetime_is_whole_directory(tmp_path):
    first = clean(tmp_path)
    new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    outside = tmp_path / "outside"
    outside.mkdir(); (outside / "angmoo.sqlite3").write_bytes(b"protected outside")
    junction = tmp_path / "canonical" / "generations" / "junction"
    if sys.platform == "win32":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    else:
        junction.symlink_to(outside, target_is_directory=True)
    target = first.canonical.database_path.parent
    for suffix in ("-wal", "-shm"):
        (target / ("angmoo.sqlite3" + suffix)).write_bytes(b"closed obsolete fixture")
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    try:
        assert prune(tmp_path, owner)["removed"] == 1
        assert not target.exists() and (outside / "angmoo.sqlite3").read_bytes() == b"protected outside"
        assert junction.exists()
    finally:
        owner.close()


@pytest.mark.parametrize("fault", ["finalize", "promote", "post_validate", "source_changed"])
def test_upgrade_failure_preserves_source_and_unconfirmed_final(tmp_path, monkeypatch, fault):
    source = _seed_v1(tmp_path, with_graph=False)
    before = source.read_bytes()
    if fault == "finalize":
        monkeypatch.setattr(EmbeddedGenerationController, "finalize_staging", lambda *a, **k: (_ for _ in ()).throw(OSError("finalize")))
    elif fault == "promote":
        monkeypatch.setattr(EmbeddedGenerationController, "promote", lambda *a, **k: (_ for _ in ()).throw(OSError("promote")))
    elif fault == "post_validate":
        original = migration._validate_database
        def validate(path, manifest):
            original(path, manifest)
            if path.parent != source.parent and not path.parent.name.startswith("."):
                raise migration.SqliteCanonicalUpgradeError("injected_post_validate")
        monkeypatch.setattr(migration, "_validate_database", validate)
    else:
        original = migration._backup_database
        def backup(old, new):
            original(old, new)
            with sqlite3.connect(old) as db:
                db.execute("UPDATE users SET display_name='Changed during fixture upgrade'")
        monkeypatch.setattr(migration, "_backup_database", backup)
    with pytest.raises((OSError, migration.SqliteCanonicalUpgradeError)):
        EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation=source.parent.name).upgrade()
    if fault != "source_changed":
        assert source.read_bytes() == before
    for directory in source.parent.parent.iterdir():
        ownership = directory / retention.OWNERSHIP_FILE
        if ownership.exists():
            assert not retention._read(ownership, retention.GenerationOwnership).promotion_confirmed
    assert source.exists()


def test_previous_replacement_then_current_failure_preserves_all_generations(tmp_path, monkeypatch):
    from app.runtime.migrations import generation
    first = clean(tmp_path)
    new_copy(tmp_path, name="B")
    current_path = tmp_path / "canonical" / "current-generation.json"
    before = snapshot(tmp_path / "canonical" / "generations")
    original = generation._write_json_atomic
    def fail_current(path, payload):
        if path == current_path: raise OSError("injected current marker replacement")
        return original(path, payload)
    monkeypatch.setattr(generation, "_write_json_atomic", fail_current)
    with pytest.raises(OSError, match="current marker replacement"):
        new_copy(tmp_path, name="C")
    assert json.loads(current_path.read_text())["relative_path"] == "generations/B"
    assert (tmp_path / "canonical" / "previous-generation.json").read_bytes() == current_path.read_bytes()
    final = tmp_path / "canonical" / "generations" / "C"
    assert not retention._read(final / retention.OWNERSHIP_FILE, retention.GenerationOwnership).promotion_confirmed
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    try:
        result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="clean").upgrade(retention_owner=owner)
        assert not result.canonical.migrated and result.canonical.generation == "B"
        assert result.retention == {"protection_ambiguous": 1}
        after = snapshot(tmp_path / "canonical" / "generations")
        assert all(after[path] == digest for path, digest in before.items())
        assert first.canonical.database_path.exists() and final.exists()
    finally:
        owner.close()


def test_removal_intent_write_failure_defers_without_copy_or_startup_failure(tmp_path, monkeypatch):
    first = clean(tmp_path)
    new_copy(tmp_path, name="B"); new_copy(tmp_path, name="C")
    before = first.canonical.database_path.read_bytes()
    original = retention._atomic_json
    def fail_intent(path, payload):
        if path.parent.name == "canonical-removals": raise OSError("injected removal intent write")
        return original(path, payload)
    owner = retention.ServingRetentionOwner(tmp_path).acquire()
    monkeypatch.setattr(migration, "_backup_database", lambda *a: pytest.fail("unnecessary copy"))
    try:
        monkeypatch.setattr(retention, "_atomic_json", fail_intent)
        result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="clean").upgrade(retention_owner=owner)
        assert result.canonical.generation == "C" and not result.canonical.migrated
        assert result.retention["deferred"] == 1
        assert first.canonical.database_path.read_bytes() == before
        assert list((tmp_path / "runtime" / "canonical-removals").glob("*.json")) == []
        monkeypatch.setattr(retention, "_atomic_json", original)
        result = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(tmp_path), fallback_generation="clean").upgrade(retention_owner=owner)
        assert not result.canonical.migrated and not first.canonical.database_path.exists()
    finally:
        owner.close()
