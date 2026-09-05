"""Generate or verify the append-only P8-L-B Chat domain parity inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "security/p8_l_b_chat_domain_policy.json"
OUTPUT_PATH = ROOT / "security/p8_l_b_chat_domain_inventory.json"
SUCCESSOR_INVENTORY_PATH = (
    ROOT / "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
)
FROZEN_OUTPUT_SHA256 = (
    "d9e5b83d78059d91629f001e48d3031bd44a495f625be1588f00770395c5d70e"
)


class InventoryError(RuntimeError):
    """Stable failure for a missing or drifting P8-L-B invariant."""


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InventoryError(f"{path}: root must be an object")
    return value


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def _record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise InventoryError(f"required file is missing: {relative}")
    data = _normalized_bytes(path)
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == name and value is not None:
            try:
                return ast.literal_eval(value)
            except (TypeError, ValueError):
                return None
    return None


def _module_name(relative: str) -> str:
    value = Path(relative).with_suffix("").as_posix().replace("backend/", "").replace("/", ".")
    return value.removesuffix(".__init__")


def _architecture(policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    baseline = _json(ROOT / policy["architecture_inventory"])
    modules = {item["module"]: item for item in baseline["modules"]}
    required_modules = {
        _module_name(path)
        for path in policy["required_files"]
        if path.startswith("backend/app/")
    }
    missing = sorted(required_modules - modules.keys())
    if missing:
        raise InventoryError(
            "architecture inventory is stale or incomplete; missing modules: "
            + ", ".join(missing)
        )
    for module, expected in policy["required_module_imports"].items():
        actual = set(modules.get(module, {}).get("imports", []))
        absent = sorted(set(expected) - actual)
        if absent:
            raise InventoryError(f"{module}: required imports missing: {absent}")
    return baseline, modules


def _legacy_edges(
    policy: dict[str, Any], modules: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    expected = {tuple(item) for item in policy["legacy_message_edges"]}
    found = []
    for importer, imported in sorted(expected):
        if imported in modules.get(importer, {}).get("imports", []):
            found.append({"importer": importer, "imported": imported})
    return found


def _pure_layer_violations(
    policy: dict[str, Any], modules: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    internal_prefixes = tuple(policy["pure_layer_forbidden_internal_prefixes"])
    external_prefixes = tuple(policy["pure_layer_forbidden_external_prefixes"])
    pure_prefixes = tuple(policy["pure_layer_prefixes"])
    for module, item in sorted(modules.items()):
        if not module.startswith(pure_prefixes):
            continue
        for imported in item.get("imports", []):
            if imported.startswith(internal_prefixes):
                violations.append(
                    {"kind": "internal", "importer": module, "imported": imported}
                )
        for imported in item.get("external_imports", []):
            if imported.startswith(external_prefixes):
                violations.append(
                    {"kind": "external", "importer": module, "imported": imported}
                )
    return violations


def _route_operations() -> list[str]:
    path = ROOT / "backend/app/api/v1/routes/messages.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    operations: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "router"
                and func.attr in {"get", "post", "patch", "delete"}
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            operations.add(f"{func.attr.upper()} /api/v1{decorator.args[0].value}")
    return sorted(operations)


def _tables() -> list[str]:
    path = ROOT / "backend/app/domains/chat/infrastructure/sqlalchemy_models.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tables = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id == "__tablename__"
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                tables.append(statement.value.value)
    return sorted(tables)


def _alembic() -> dict[str, Any]:
    revisions: dict[str, dict[str, Any]] = {}
    referenced: set[str] = set()
    for path in sorted((ROOT / "backend/alembic/versions").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _assignment(tree, "revision")
        down_revision = _assignment(tree, "down_revision")
        if not isinstance(revision, str):
            continue
        if revision in revisions:
            raise InventoryError(f"duplicate Alembic revision: {revision}")
        revisions[revision] = {
            "path": path.relative_to(ROOT).as_posix(),
            "down_revision": down_revision,
        }
        if isinstance(down_revision, str):
            referenced.add(down_revision)
        elif isinstance(down_revision, (tuple, list)):
            referenced.update(item for item in down_revision if isinstance(item, str))
    heads = sorted(set(revisions) - referenced)
    return {
        "revision_count": len(revisions),
        "heads": heads,
    }


def _service_contract(policy: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / "backend/app/domains/chat/domain/policies.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    expected = policy["service_contract"]
    actual = {
        name: _assignment(tree, name)
        for name in expected
        if name != "provider_calls_per_attempt"
    }
    runtime_text = (ROOT / "backend/app/runtime/chat/sqlalchemy_service.py").read_text(
        encoding="utf-8"
    )
    actual["provider_calls_per_attempt"] = len(
        re.findall(r"RunLlmTracker\(\s*max_calls\s*=\s*1\s*\)", runtime_text)
    )
    return actual


def _validate_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise InventoryError(f"{label} drift: expected={expected!r} actual={actual!r}")


def build_inventory() -> dict[str, Any]:
    policy = _json(POLICY_PATH)
    predecessor = policy["predecessor"]
    predecessor_record = _record(predecessor["path"])
    _validate_equal(
        "P8-L-A predecessor digest",
        predecessor_record["sha256"],
        predecessor["sha256"],
    )

    baseline, modules = _architecture(policy)
    legacy_edges = _legacy_edges(policy, modules)
    pure_violations = _pure_layer_violations(policy, modules)
    _validate_equal("frozen legacy message edges", legacy_edges, [])
    _validate_equal("pure Chat layer violations", pure_violations, [])

    routes = _route_operations()
    tables = _tables()
    service_contract = _service_contract(policy)
    _validate_equal("Chat v1 route operations", routes, policy["required_route_operations"])
    _validate_equal("Chat v1 tables", tables, policy["required_tables"])
    _validate_equal("Chat v1 service contract", service_contract, policy["service_contract"])

    alembic = _alembic()
    migration_policy = policy["migration_baseline"]
    _validate_equal(
        "Alembic revision count",
        alembic["revision_count"],
        migration_policy["alembic_revision_count"],
    )
    _validate_equal("Alembic heads", alembic["heads"], [migration_policy["alembic_head"]])
    embedded = _json(ROOT / migration_policy["embedded_manifest"])
    embedded_view = {
        "schema_version": embedded["schema_version"],
        "source_revision": embedded["source_revision"],
        "source_migration_count": embedded["source_migration_count"],
        "canonical_table_count": embedded["canonical_table_count"],
        "schema_digest": embedded["schema_digest"],
    }
    expected_embedded = {
        "schema_version": migration_policy["embedded_schema_version"],
        "source_revision": migration_policy["embedded_source_revision"],
        "source_migration_count": migration_policy["embedded_source_migration_count"],
        "canonical_table_count": migration_policy["embedded_canonical_table_count"],
        "schema_digest": migration_policy["embedded_schema_digest"],
    }
    _validate_equal("embedded SQLite v3 manifest", embedded_view, expected_embedded)

    selected_names = sorted(
        set(policy["required_module_imports"])
        | {
            "app.domains.chat.public",
            "app.domains.chat.api.schemas",
            "app.domains.chat.domain.errors",
            "app.domains.chat.domain.policies",
            "app.domains.chat.application.messages",
            "app.domains.chat.ports.runtime",
            "app.domains.chat.infrastructure.sqlalchemy_models",
            "app.runtime.chat.sqlalchemy_service",
            "app.runtime.chat.sqlalchemy_adapter",
            "app.runtime.chat.model_bindings",
        }
    )
    selected_modules = [
        {
            "module": name,
            "path": modules[name]["path"],
            "imports": modules[name].get("imports", []),
            "external_imports": modules[name].get("external_imports", []),
        }
        for name in selected_names
    ]
    return {
        "schema_version": policy["schema_version"],
        "policy_id": policy["policy_id"],
        "owner_stage": policy["owner_stage"],
        "predecessor": predecessor_record,
        "policy": _record(POLICY_PATH.relative_to(ROOT).as_posix()),
        "documentation": _record(policy["documentation"]),
        "architecture": {
            "baseline": _record(policy["architecture_inventory"]),
            "module_count": baseline["module_count"],
            "internal_edge_count": baseline["edge_count"],
            "external_import_count": baseline["external_import_count"],
            "selected_modules": selected_modules,
            "removed_frozen_legacy_edge_count": len(policy["legacy_message_edges"]),
            "remaining_frozen_legacy_edges": legacy_edges,
            "pure_layer_violations": pure_violations,
        },
        "required_files": [_record(path) for path in policy["required_files"]],
        "compatibility_exports": policy["compatibility_exports"],
        "profile_ref_contract": policy["profile_ref_contract"],
        "route_operations": routes,
        "tables": tables,
        "message_migrations": [_record(path) for path in policy["required_message_migrations"]],
        "migration_baseline": {
            "alembic": alembic,
            "embedded_sqlite": embedded_view,
        },
        "service_contract": service_contract,
        "postgres_concurrency_status": policy["postgres_concurrency_status"],
    }


def _check_frozen_successor_boundary() -> None:
    """Verify the immutable B artifact once append-only stage D owns current-tree drift."""

    if _sha256(OUTPUT_PATH) != FROZEN_OUTPUT_SHA256:
        raise InventoryError("frozen P8-L-B inventory digest drift")
    inventory = _json(OUTPUT_PATH)
    predecessor = inventory.get("predecessor")
    if not isinstance(predecessor, dict):
        raise InventoryError("frozen P8-L-B predecessor is missing")
    predecessor_path = ROOT / str(predecessor.get("path") or "")
    if (
        not predecessor_path.is_file()
        or _sha256(predecessor_path) != predecessor.get("sha256")
    ):
        raise InventoryError("frozen P8-L-A predecessor digest drift")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if SUCCESSOR_INVENTORY_PATH.is_file():
            if args.write:
                raise InventoryError(
                    "P8-L-B inventory is frozen; current-tree ownership moved to P8-L-D"
                )
            _check_frozen_successor_boundary()
            print("P8-L-B Chat domain inventory is frozen and chained to P8-L-D")
            return 0
        inventory = build_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError(f"generated inventory is missing: {OUTPUT_PATH.relative_to(ROOT)}")
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-B inventory drift; run "
                "python scripts/ci/generate_p8_l_b_chat_domain_inventory.py --write"
            )
        print("P8-L-B Chat domain inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, SyntaxError, json.JSONDecodeError) as exc:
        print(f"P8-L-B inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
