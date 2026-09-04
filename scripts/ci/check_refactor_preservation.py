"""Compare the current refactor against its frozen source and behavior baseline.

The baseline is historical evidence, never a snapshot to regenerate after a move.
Test renames are explicit and one-to-one; additional tests remain welcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "security/refactor_source_baseline.json"
INVENTORY = ROOT / "security/refactor_feature_inventory.json"
MOVES = ROOT / "security/refactor_path_map.json"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def current_contracts() -> dict:
    # Import without lifespan: no DB initialization, scheduler, or provider call.
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app as full_app
    from app.public_main import app as public_app
    import app.models  # noqa: F401 - canonical model registration
    from app.core.db import Base

    contracts = {}
    for name, application in (("full", full_app), ("public", public_app)):
        schema = application.openapi()
        contracts[name] = {
            "operations": {f"{method.upper()} {path}": digest(operation)
                           for path, methods in sorted(schema["paths"].items())
                           for method, operation in sorted(methods.items())},
            "schemas": {name: digest(value) for name, value in sorted(schema.get("components", {}).get("schemas", {}).items())},
        }
    contracts["orm_tables"] = {
        name: digest({
            "columns": [{"name": col.name, "type": str(col.type), "nullable": col.nullable,
                         "primary_key": col.primary_key,
                         "foreign_keys": sorted(fk.target_fullname for fk in col.foreign_keys)}
                        for col in table.columns],
            "indexes": sorted((idx.name or "", idx.unique, sorted(col.name for col in idx.columns)) for idx in table.indexes),
        }) for name, table in sorted(Base.metadata.tables.items())
    }
    return contracts


def missing_nodes(approved: list[str], current: list[str], moves: dict[str, str]) -> list[str]:
    if len(set(moves.values())) != len(moves):
        raise ValueError("test node moves must be one-to-one")
    unknown = set(moves) - set(approved)
    if unknown:
        raise ValueError(f"test moves absent from frozen baseline: {sorted(unknown)}")
    return sorted({moves.get(node, node) for node in approved} - set(current))


def check_inventory(inventory: dict, baseline: dict, root: Path = ROOT) -> list[str]:
    errors = []
    if inventory.get("baseline_commit") != baseline["commit"]:
        errors.append("feature inventory baseline commit differs")
    items = inventory.get("items", [])
    ids = [item["id"] for item in items]
    required = {f"K{i:02}" for i in range(1, 24)} | {f"G{i:02}" for i in range(1, 14)}
    if len(ids) != len(set(ids)) or required - set(ids):
        errors.append("K01-K23/G01-G13 coverage is incomplete or duplicated")
    for item in items:
        for field in ("owner", "stage", "preserved_contracts", "current_paths", "target_paths", "verification", "disposition"):
            if not item.get(field):
                errors.append(f"{item['id']}: missing {field}")
        if item.get("status") not in {"MAPPED", "MOVED", "VERIFIED", "PROVEN_UNUSED"}:
            errors.append(f"{item['id']}: unresolved status")
        for path in item.get("current_paths", []) + item.get("test_paths", []):
            candidate = (root / path).resolve()
            if not candidate.is_relative_to(root.resolve()) or not candidate.exists():
                errors.append(f"{item['id']}: missing or unsafe path {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", action="store_true")
    parser.add_argument("--nodes", action="store_true")
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    moves = json.loads(MOVES.read_text(encoding="utf-8"))
    errors = check_inventory(inventory, baseline)
    for old in baseline["tracked_files"]:
        target = moves["files"].get(old, old)
        path = (ROOT / target).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            errors.append(f"source missing without a surviving mapped destination: {old} -> {target}")
    if args.contracts:
        contracts = current_contracts()
        for name, values in baseline["contracts"].items():
            if contracts.get(name) != values:
                errors.append(f"API/ORM contract changed: {name}; investigate, do not regenerate the frozen baseline")
    if args.nodes:
        result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
                                cwd=ROOT / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            errors.append("pytest collection failed: " + result.stderr[-2000:])
        else:
            nodes = [line.strip() for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line]
            errors.extend("missing test: " + node for node in missing_nodes(baseline["test_nodes"], nodes, moves["test_nodes"]))
            print(f"Frozen backend nodes={len(baseline['test_nodes'])}; current={len(nodes)}")
    for message in errors:
        print(message, file=sys.stderr)
    if not errors:
        print(f"Refactor preservation passed: items={len(inventory['items'])}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
