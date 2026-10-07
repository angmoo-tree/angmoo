"""Explicit, audited D03 maintenance for a stopped contributor runtime.

inspect is read-only. upgrade uses the canonical copy-on-write upgrader and the
root's own secret. apply consumes the reviewed exact inventory, rechecks it
under a transaction, and preserves every table outside the declared old queue.
This tool never starts workers or calls a provider.
"""
from pathlib import Path
from datetime import UTC, datetime
from dataclasses import asdict
from hashlib import sha256
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.migrations.generation import EmbeddedGenerationController, EmbeddedUpgradeLock
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.repository.situation_transition import inspect_discard, LegacyDiscardPlan
from app.runtime.memory.situation_retirement import discard

MUTABLE = frozenset({
    "memory_maintenance_jobs", "memory_batch_runs", "memory_selection_decisions", "memory_candidates",
    "memory_source_deliveries", "memory_activation_epochs", "memory_episode_bundles", "memory_episode_units",
    "memory_episode_unit_evidence", "memory_episode_processed_units", "memory_episode_links",
    "memory_consolidation_requests", "memory_consolidation_jobs", "relationship_review_requests",
    "memory_situation_transitions",
})


def fingerprint(connection):
    result = {}
    for name, in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = connection.exec_driver_sql(f"SELECT * FROM {quoted}")
        hashes = sorted(sha256(repr(tuple(row)).encode()).hexdigest() for row in rows)
        result[name] = {"count": len(hashes), "sha256": sha256("".join(hashes).encode()).hexdigest()}
    return result


def database(root):
    canonical = root / "canonical"
    relative = EmbeddedGenerationController(canonical, artifact_relative_path="angmoo.sqlite3").selected_relative_path("generations/contributor-v1")
    path = (canonical / relative / "angmoo.sqlite3").resolve(strict=True)
    if not path.is_relative_to(canonical.resolve()):
        raise ValueError("retirement_root_escape")
    return path


def engine_for(path, *, readonly=False):
    url = f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true" if readonly else f"sqlite:///{path.as_posix()}"
    engine = create_engine(url)
    event.listen(engine, "connect", lambda db, _: db.execute("PRAGMA foreign_keys=ON"))
    return engine


def inspect_root(root):
    path = database(root)
    engine = engine_for(path, readonly=True)
    with Session(engine) as db:
        identities = fingerprint(db.connection())
        plans = [asdict(inspect_discard(db, identifier)) for identifier in db.scalars(select(MemoryScopeSettingModel.id).order_by(MemoryScopeSettingModel.id))]
    engine.dispose()
    return {"root": str(root), "database": str(path), "policy": "episode-activity-batch32.v1",
        "captured_at": datetime.now(UTC).isoformat(), "tables": identities, "plans": plans,
        "secret_sha256": sha256((root / "secrets/app-secret").read_bytes()).hexdigest()}


def assert_inventory(root, inventory):
    if str(root) != inventory["root"] or inventory["policy"] != "episode-activity-batch32.v1":
        raise ValueError("retirement_inventory_scope_mismatch")
    if sha256((root / "secrets/app-secret").read_bytes()).hexdigest() != inventory["secret_sha256"]:
        raise ValueError("retirement_secret_changed")


def upgrade(root, inventory):
    assert_inventory(root, inventory)
    current = inspect_root(root)
    # The persisted CLI inventory has JSON arrays; dataclass snapshots use tuples.
    # Compare the serialized contract rather than Python container types.
    if json.dumps(current["plans"], sort_keys=True) != json.dumps(inventory["plans"], sort_keys=True):
        raise ValueError("retirement_inventory_changed")
    from app.config import settings
    from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
    from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator
    owned = settings.model_copy(update={"APP_SECRET_FILE": str(root / "secrets/app-secret")})
    with EmbeddedUpgradeLock(root / "runtime/embedded-data-migration.lock"):
        result = SqliteCanonicalUpgradeCoordinator(StaticRuntimeDataPath(root), fallback_generation="contributor-v1",
            secret_interpreter=MigrationSecretInterpreter(secret_source=lambda: owned.app_secret)).upgrade()
    assert_inventory(root, inventory)
    return {"source_version": result.source_version, "target_version": result.target_version,
        "migrated": result.migrated, "database": str(result.database_path), "providers_called": 0}


def apply_inventory(root, inventory):
    assert_inventory(root, inventory)
    engine = engine_for(database(root))
    audit_key = "d03:" + sha256(json.dumps(inventory["plans"], sort_keys=True).encode()).hexdigest()
    with EmbeddedUpgradeLock(root / "runtime/embedded-data-migration.lock"), Session(engine) as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        before = fingerprint(db.connection())
        for table, expected in inventory["tables"].items():
            if table not in MUTABLE and table not in {"angmoo_schema_version", "alembic_version"} and before.get(table) != expected:
                raise ValueError("retirement_preserved_table_changed:" + table)
        plans = [LegacyDiscardPlan(row["setting_id"], row["cutoff"], tuple(row["job_ids"]), tuple(row["candidate_ids"]), tuple(row["request_ids"])) for row in inventory["plans"]]
        for plan in plans:
            discard(db, plan, request_key=audit_key, now=datetime.now(UTC))
        after = fingerprint(db.connection())
        changed = sorted(name for name in before if before[name] != after.get(name))
        if set(changed) - MUTABLE:
            raise ValueError("retirement_preservation_failed:" + ",".join(sorted(set(changed)-MUTABLE)))
        if db.connection().exec_driver_sql("PRAGMA foreign_key_check").all():
            raise ValueError("retirement_foreign_key_check_failed")
        for plan in plans:
            remaining = inspect_discard(db, plan.setting_id)
            if remaining.job_ids or remaining.candidate_ids or remaining.request_ids:
                raise ValueError("retirement_work_remaining")
        db.commit()
    engine.dispose()
    assert_inventory(root, inventory)
    return {"audit_key": audit_key, "scopes": len(plans), "deleted_jobs": sum(len(p.job_ids) for p in plans),
        "deleted_candidates": sum(len(p.candidate_ids) for p in plans), "deleted_requests": sum(len(p.request_ids) for p in plans),
        "remaining_target_work": 0, "changed_tables": changed,
        "preserved_tables": len(before)-len(changed), "before": before, "after": after, "providers_called": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "upgrade", "apply"))
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    register_models()
    root = args.data_root.resolve(strict=True)
    if args.mode == "inspect":
        result = inspect_root(root)
        args.inventory.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"scopes": len(result["plans"]), "jobs": sum(len(p["job_ids"]) for p in result["plans"]),
            "candidates": sum(len(p["candidate_ids"]) for p in result["plans"]), "read_only": True}))
    else:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = upgrade(root, inventory) if args.mode == "upgrade" else apply_inventory(root, inventory)
        if args.audit:
            args.audit.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key not in {"before", "after"}}))
