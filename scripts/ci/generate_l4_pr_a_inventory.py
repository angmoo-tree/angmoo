"""Generate and verify the deterministic L4 PR A P5-P7 baseline inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "security/l4_pr_a_inventory_policy.json"
DEFAULT_OUTPUT = ROOT / "security/l4_pr_a_inventory.json"
FRONTEND_IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]"
)
FRONTEND_EXPORT_PATTERN = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|type|interface)\s+([A-Za-z0-9_]+)",
    re.MULTILINE,
)
WORKFLOW_JOB_PATTERN = re.compile(r"^  ([a-zA-Z0-9_-]+):\s*$", re.MULTILINE)


class L4InventoryError(RuntimeError):
    """Stable failure for a stale or invalid L4 PR A inventory."""


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise L4InventoryError(f"{path}: root must be an object")
    return payload


def _sha256(path: Path) -> str:
    # Every inventoried artifact is repository text.  Hash its canonical Git
    # representation so Windows CRLF checkouts and Linux CI checkouts produce
    # the same frozen inventory.
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _path_record(relative: str, *, root: Path) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise L4InventoryError(f"required inventory file is missing: {relative}")
    return {"path": relative, "sha256": _sha256(path)}


def _architecture_inventory(*, root: Path) -> dict[str, Any]:
    payload = _load_json(root / "security/architecture_import_baseline.json")
    required = {"schema_version", "module_count", "edge_count", "external_import_count", "modules"}
    if not required.issubset(payload):
        raise L4InventoryError("architecture import baseline has an unsupported shape")
    return payload


def _selected_backend_modules(
    architecture: dict[str, Any],
    ownership: dict[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for owner, prefixes in sorted(ownership.items()):
        selected = []
        for item in architecture["modules"]:
            module = item["module"]
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes):
                selected.append(
                    {
                        "imports": item["imports"],
                        "module": module,
                        "path": item["path"],
                    }
                )
        result[owner] = sorted(selected, key=lambda value: value["module"])
    return result


def _module_cycles(architecture: dict[str, Any]) -> list[list[str]]:
    graph = {
        item["module"]: [target for target in item["imports"]]
        for item in architecture["modules"]
    }
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, []):
            if target not in graph:
                continue
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            current = stack.pop()
            on_stack.remove(current)
            component.append(current)
            if current == node:
                break
        if len(component) > 1 or node in graph.get(node, []):
            components.append(sorted(component))

    for module in sorted(graph):
        if module not in indices:
            visit(module)
    return sorted(components)


def _frontend_imports(path: Path) -> list[str]:
    return sorted(set(FRONTEND_IMPORT_PATTERN.findall(path.read_text(encoding="utf-8"))))


def _frontend_record(relative: str, *, root: Path) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise L4InventoryError(f"frontend inventory file is missing: {relative}")
    text = path.read_text(encoding="utf-8")
    return {
        "exports": sorted(set(FRONTEND_EXPORT_PATTERN.findall(text))),
        "imports": _frontend_imports(path),
        "path": relative,
        "sha256": _sha256(path),
    }


def _alias_for_frontend_path(relative: str) -> str:
    prefix = "frontend/src/"
    suffix = relative[len(prefix) :] if relative.startswith(prefix) else relative
    for extension in (".tsx", ".ts"):
        if suffix.endswith(extension):
            suffix = suffix[: -len(extension)]
    if suffix.endswith("/index"):
        suffix = suffix[: -len("/index")]
    return f"@/{suffix}"


def _frontend_consumers(
    candidates: list[str],
    *,
    root: Path,
) -> dict[str, list[str]]:
    source_root = root / "frontend/src"
    source_files = sorted(
        path for path in source_root.rglob("*") if path.suffix in {".ts", ".tsx"}
    )
    aliases = {_alias_for_frontend_path(path): path for path in candidates}
    consumers: dict[str, list[str]] = {path: [] for path in candidates}
    for source in source_files:
        imports = set(_frontend_imports(source))
        source_relative = source.relative_to(root).as_posix()
        for alias, candidate in aliases.items():
            if alias in imports:
                consumers[candidate].append(source_relative)
    return {path: sorted(values) for path, values in sorted(consumers.items())}


def _frontend_public_surfaces(*, root: Path) -> dict[str, list[str]]:
    feature_root = root / "frontend/src/features"
    shared_root = root / "frontend/src/shared"
    return {
        "features": sorted(
            path.relative_to(root).as_posix()
            for path in feature_root.glob("*/public.ts")
        ),
        "shared": sorted(
            path.relative_to(root).as_posix()
            for path in shared_root.glob("*/public.ts")
        ),
    }


def _python_test_nodes(relative: str, *, root: Path) -> list[str]:
    path = root / relative
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{relative}::{node.name}"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _manifest_record(relative: str, *, root: Path) -> dict[str, Any]:
    path = root / relative
    payload = _load_json(path)
    selected = {
        key: payload[key]
        for key in (
            "canonical_table_count",
            "minimum_ladybug_version",
            "parity_contract_version",
            "projection_schema_version",
            "schema_digest",
            "schema_version",
            "source_migration_count",
            "source_revision",
        )
        if key in payload
    }
    return {"contract": selected, "path": relative, "sha256": _sha256(path)}


def _validate_policy(policy: dict[str, Any], *, root: Path) -> None:
    if policy.get("schema_version") != 1:
        raise L4InventoryError("policy.schema_version must be 1")
    if policy.get("policy_id") != "angmoo-l4-pr-a-p5-p7-inventory-v1":
        raise L4InventoryError("policy.policy_id is invalid")
    baseline = str(policy.get("baseline_commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise L4InventoryError("policy.baseline_commit must be an exact SHA")
    for relative, markers in policy["frontend"]["required_ui_markers"].items():
        text = (root / relative).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise L4InventoryError(f"{relative}: missing UI markers {missing}")


def build_inventory(*, root: Path = ROOT, policy_path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = _load_json(policy_path)
    _validate_policy(policy, root=root)
    architecture = _architecture_inventory(root=root)
    architecture_policy = _load_json(root / "security/architecture_import_policy.json")
    backend_modules = _selected_backend_modules(
        architecture,
        policy["backend_ownership"],
    )

    frontend_paths = list(policy["frontend"]["current_candidates"])
    for pattern in policy["frontend"]["current_route_globs"]:
        frontend_paths.extend(
            path.relative_to(root).as_posix() for path in root.glob(pattern)
        )
    frontend_paths = sorted(set(frontend_paths))
    frontend_consumers = _frontend_consumers(frontend_paths, root=root)

    test_nodes = sorted(
        node
        for relative in policy["parity_test_files"]
        for node in _python_test_nodes(relative, root=root)
    )
    node_set = set(test_nodes)
    missing_counter_tests = sorted(
        item["test"] for item in policy["behavior_counters"] if item["test"] not in node_set
    )
    if missing_counter_tests:
        raise L4InventoryError(
            f"behavior counter tests are missing: {missing_counter_tests}"
        )

    workflow_text = (root / ".github/workflows/windows-installer.yml").read_text(
        encoding="utf-8"
    )
    observed_jobs = sorted(set(WORKFLOW_JOB_PATTERN.findall(workflow_text)))
    missing_jobs = sorted(set(policy["installer_jobs"]) - set(observed_jobs))
    if missing_jobs:
        raise L4InventoryError(f"Windows installer jobs are missing: {missing_jobs}")

    migration = policy["migration_contracts"]
    return {
        "architecture": {
            "backend": {
                "external_import_count": architecture["external_import_count"],
                "internal_edge_count": architecture["edge_count"],
                "legacy_import_exception_count": len(
                    architecture_policy.get("legacy_import_exceptions", [])
                ),
                "module_count": architecture["module_count"],
                "module_cycles": _module_cycles(architecture),
                "policy_allowed_cycle_count": len(
                    architecture_policy.get("allowed_module_cycles", [])
                ),
                "ownership": backend_modules,
            },
            "frontend": {
                "candidate_count": len(frontend_paths),
                "candidate_consumer_edge_count": sum(
                    len(values) for values in frontend_consumers.values()
                ),
                "candidate_consumers": frontend_consumers,
                "current_candidates": [
                    _frontend_record(relative, root=root) for relative in frontend_paths
                ],
                "planned_feature_allowlist": policy["frontend"][
                    "planned_feature_allowlist"
                ],
                "public_surfaces": _frontend_public_surfaces(root=root),
            },
        },
        "baseline_commit": policy["baseline_commit"],
        "behavior": {
            "counter_contracts": policy["behavior_counters"],
            "oracle_artifacts": [
                _path_record(relative, root=root)
                for relative in policy["oracle_artifacts"]
            ],
            "parity_test_files": [
                _path_record(relative, root=root)
                for relative in policy["parity_test_files"]
            ],
            "parity_test_node_count": len(test_nodes),
            "parity_test_nodes": test_nodes,
        },
        "documentation": policy["documentation"],
        "forbidden_changes": policy["forbidden_changes"],
        "installer": {
            "required_jobs": policy["installer_jobs"],
            "workflow": ".github/workflows/windows-installer.yml",
            "workflow_sha256": _sha256(root / ".github/workflows/windows-installer.yml"),
        },
        "policy_id": policy["policy_id"],
        "runtime": {
            "ladybug": {
                "manifests": [
                    _manifest_record(relative, root=root)
                    for relative in migration["ladybug_manifests"]
                ],
                "registry": _path_record(migration["ladybug_registry"], root=root),
            },
            "sqlite": {
                "manifests": [
                    _manifest_record(relative, root=root)
                    for relative in migration["sqlite_manifests"]
                ],
                "registry": _path_record(migration["sqlite_registry"], root=root),
                "steps": [
                    _path_record(relative, root=root)
                    for relative in migration["sqlite_steps"]
                ],
            },
        },
        "schema_version": 1,
    }


def render(*, root: Path = ROOT, policy_path: Path = DEFAULT_POLICY) -> str:
    return json.dumps(
        build_inventory(root=root, policy_path=policy_path),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.write and not args.check:
        parser.error("use --write or --check")
    try:
        rendered = render(policy_path=args.policy)
        if args.write:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        if args.check:
            if not args.output.is_file():
                raise L4InventoryError("L4 PR A inventory is missing")
            if args.output.read_text(encoding="utf-8") != rendered:
                raise L4InventoryError("L4 PR A inventory is stale")
        payload = json.loads(rendered)
    except (OSError, UnicodeError, json.JSONDecodeError, SyntaxError, L4InventoryError) as exc:
        print(f"L4 PR A inventory failed: {exc}", file=sys.stderr)
        return 1
    print(
        "L4 PR A inventory passed: "
        f"backend_modules={payload['architecture']['backend']['module_count']} "
        f"frontend_candidates={len(payload['architecture']['frontend']['current_candidates'])} "
        f"parity_nodes={payload['behavior']['parity_test_node_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
