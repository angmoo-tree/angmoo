"""Enforce Angmoo's T2.5 domain-first import policy."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = ROOT / "security/architecture_import_baseline.json"
DEFAULT_POLICY = ROOT / "security/architecture_import_policy.json"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: root must be an object")
    return payload


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _edge_label(importer: str, imported: str) -> str:
    return f"{importer} -> {imported}"


def _violation(
    *,
    rule: str,
    importer: str,
    imported: str,
    suggestion: str,
    exception: dict[str, Any] | None = None,
) -> str:
    exception_state = "yes" if exception else "no"
    owner = str(exception.get("owner_stage")) if exception else "none"
    return (
        f"[{rule}] {_edge_label(importer, imported)}; "
        f"allowed_fix={suggestion}; legacy_exception={exception_state}; "
        f"owner_stage={owner}; docs=docs/architecture/backend-domains.md"
    )


def _inventory_modules(
    inventory: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    if inventory.get("schema_version") != 2:
        errors.append("inventory schema_version must be 2")
    raw_modules = inventory.get("modules")
    if not isinstance(raw_modules, list):
        return {}, errors + ["inventory.modules must be an array"]

    modules: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for index, item in enumerate(raw_modules):
        label = f"inventory.modules[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        name = item.get("module")
        path = item.get("path")
        if not isinstance(name, str) or not name.startswith("app"):
            errors.append(f"{label}.module must be an app module")
            continue
        if name in modules:
            errors.append(f"{label}.module duplicates {name}")
        if not isinstance(path, str) or not path.startswith("backend/app/"):
            errors.append(f"{label}.path must stay under backend/app")
        elif path in paths:
            errors.append(f"{label}.path duplicates {path}")
        paths.add(str(path))
        for field in ("imports", "external_imports", "wildcard_imports"):
            values = item.get(field)
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                errors.append(f"{label}.{field} must be a string array")
            elif values != sorted(set(values)):
                errors.append(f"{label}.{field} must be sorted and unique")
        modules[name] = item

    internal_count = sum(len(item.get("imports", [])) for item in modules.values())
    external_count = sum(
        len(item.get("external_imports", [])) for item in modules.values()
    )
    if inventory.get("module_count") != len(modules):
        errors.append("inventory.module_count does not match modules")
    if inventory.get("edge_count") != internal_count:
        errors.append("inventory.edge_count does not match internal imports")
    if inventory.get("external_import_count") != external_count:
        errors.append(
            "inventory.external_import_count does not match external imports"
        )
    return modules, errors


def _validate_policy(
    policy: dict[str, Any],
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[str, ...], dict[str, Any]],
    list[str],
]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("policy schema_version must be 1")
    if policy.get("policy_id") != "angmoo-t2-5-domain-first-v1":
        errors.append("policy_id must be angmoo-t2-5-domain-first-v1")
    if policy.get("documentation") != "docs/architecture/backend-domains.md":
        errors.append("policy.documentation must point to backend domain map")

    owner_stages = policy.get("owner_stages")
    expected_stages = {"T2.5", "L0", "L1", "L2", "L3", "L4", "P8-L", "L6"}
    if not isinstance(owner_stages, list) or set(owner_stages) != expected_stages:
        errors.append("policy.owner_stages must contain the approved T2.5 stages")

    for field in (
        "legacy_prefixes",
        "new_area_prefixes",
        "pure_layer_forbidden_external_prefixes",
        "provider_sdk_prefixes",
    ):
        values = policy.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            errors.append(f"policy.{field} must be a non-empty string array")
        elif values != sorted(set(values)):
            errors.append(f"policy.{field} must be sorted and unique")

    required = {
        "id",
        "edges",
        "reason",
        "owner_stage",
        "removal_condition",
        "review_date",
    }
    exceptions: dict[tuple[str, str], dict[str, Any]] = {}
    groups = policy.get("legacy_exception_groups")
    if not isinstance(groups, list):
        errors.append("policy.legacy_exception_groups must be an array")
        groups = []
    for index, group in enumerate(groups):
        label = f"legacy_exception_groups[{index}]"
        if not isinstance(group, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = required - set(group)
        if missing:
            errors.append(f"{label} missing fields: {sorted(missing)}")
        for field in required - {"edges"}:
            if not isinstance(group.get(field), str) or not group.get(field, "").strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        if group.get("owner_stage") not in expected_stages:
            errors.append(f"{label}.owner_stage is not approved")
        try:
            date.fromisoformat(str(group.get("review_date", "")))
        except ValueError:
            errors.append(f"{label}.review_date must be an ISO date")
        edges = group.get("edges")
        if not isinstance(edges, list) or not edges:
            errors.append(f"{label}.edges must be a non-empty array")
            continue
        normalized: list[tuple[str, str]] = []
        for edge_index, edge in enumerate(edges):
            edge_label = f"{label}.edges[{edge_index}]"
            if not isinstance(edge, dict) or set(edge) != {"importer", "imported"}:
                errors.append(
                    f"{edge_label} must contain exact importer and imported fields"
                )
                continue
            importer = edge.get("importer")
            imported = edge.get("imported")
            if not isinstance(importer, str) or not isinstance(imported, str):
                errors.append(f"{edge_label} values must be strings")
                continue
            if "*" in importer or "*" in imported:
                errors.append(f"{edge_label} must not use wildcard prefixes")
            key = (importer, imported)
            if key in exceptions:
                errors.append(f"{edge_label} duplicates exact edge {_edge_label(*key)}")
            exceptions[key] = group
            normalized.append(key)
        if normalized != sorted(set(normalized)):
            errors.append(f"{label}.edges must be sorted and unique")

    cycle_required = {
        "id",
        "modules",
        "reason",
        "owner_stage",
        "removal_condition",
        "review_date",
    }
    legacy_cycles: dict[tuple[str, ...], dict[str, Any]] = {}
    cycles = policy.get("legacy_module_cycles")
    if not isinstance(cycles, list):
        errors.append("policy.legacy_module_cycles must be an array")
        cycles = []
    for index, cycle in enumerate(cycles):
        label = f"legacy_module_cycles[{index}]"
        if not isinstance(cycle, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = cycle_required - set(cycle)
        if missing:
            errors.append(f"{label} missing fields: {sorted(missing)}")
        modules = cycle.get("modules")
        if not isinstance(modules, list) or len(modules) < 2 or not all(
            isinstance(module, str) and module.startswith("app.")
            for module in modules
        ):
            errors.append(f"{label}.modules must contain at least two app modules")
            continue
        key = tuple(sorted(set(modules)))
        if list(key) != modules:
            errors.append(f"{label}.modules must be sorted and unique")
        if key in legacy_cycles:
            errors.append(f"{label} duplicates an exact legacy cycle")
        legacy_cycles[key] = cycle
        if cycle.get("owner_stage") not in expected_stages:
            errors.append(f"{label}.owner_stage is not approved")
        for field in cycle_required - {"modules"}:
            if not isinstance(cycle.get(field), str) or not cycle.get(field, "").strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        try:
            date.fromisoformat(str(cycle.get("review_date", "")))
        except ValueError:
            errors.append(f"{label}.review_date must be an ISO date")
    return exceptions, legacy_cycles, errors


def _strong_components(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in sorted(graph.get(node, set())):
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            current = stack.pop()
            on_stack.remove(current)
            component.append(current)
            if current == node:
                break
        if len(component) > 1 or node in graph.get(node, set()):
            components.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components)


def _area(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "domains"]:
        return ".".join(parts[:3])
    if len(parts) >= 3 and parts[:2] == ["app", "runtime"]:
        return ".".join(parts[:3])
    if len(parts) >= 3 and parts[:2] == ["app", "integrations"]:
        return ".".join(parts[:3])
    return None


def check_inventory(
    inventory: dict[str, Any], policy: dict[str, Any]
) -> list[str]:
    modules, errors = _inventory_modules(inventory)
    exceptions, legacy_cycles, policy_errors = _validate_policy(policy)
    errors.extend(policy_errors)
    if errors:
        return sorted(errors)

    legacy_prefixes = tuple(policy["legacy_prefixes"])
    pure_layer_forbidden_prefixes = tuple(
        policy["pure_layer_forbidden_external_prefixes"]
    )
    provider_prefixes = tuple(policy["provider_sdk_prefixes"])
    current_edges = {
        (module, imported)
        for module, item in modules.items()
        for imported in item["imports"]
    }

    for edge, exception in sorted(exceptions.items()):
        if edge not in current_edges:
            errors.append(
                _violation(
                    rule="stale_legacy_exception",
                    importer=edge[0],
                    imported=edge[1],
                    suggestion="remove the obsolete exact exception from policy",
                    exception=exception,
                )
            )

    for importer, item in sorted(modules.items()):
        for target in item["wildcard_imports"]:
            errors.append(
                _violation(
                    rule="wildcard_import",
                    importer=importer,
                    imported=target,
                    suggestion="import explicit public names",
                    exception=exceptions.get((importer, target)),
                )
            )

        importer_domain = (
            ".".join(importer.split(".")[:3])
            if importer.startswith("app.domains.")
            else None
        )
        for imported in item["imports"]:
            edge = (importer, imported)
            exception = exceptions.get(edge)
            is_legacy = any(
                _matches_prefix(imported, prefix) for prefix in legacy_prefixes
            )
            if is_legacy and exception is None:
                errors.append(
                    _violation(
                        rule="legacy_edge_not_allowlisted",
                        importer=importer,
                        imported=imported,
                        suggestion="use a domain public API; new legacy edges are forbidden",
                    )
                )

            if importer.startswith("app.core.") and any(
                _matches_prefix(imported, prefix)
                for prefix in ("app.domains", "app.runtime", "app.integrations")
            ):
                errors.append(
                    _violation(
                        rule="core_dependency_direction",
                        importer=importer,
                        imported=imported,
                        suggestion="move orchestration above app.core",
                        exception=exception,
                    )
                )

            if importer.startswith("app.integrations.") and imported.startswith(
                "app.api."
            ):
                errors.append(
                    _violation(
                        rule="integration_imports_api",
                        importer=importer,
                        imported=imported,
                        suggestion="expose an integration adapter and compose it from route/runtime",
                        exception=exception,
                    )
                )

            if importer.startswith("app.integrations.") and imported.startswith(
                "app.services."
            ) and exception is None:
                errors.append(
                    _violation(
                        rule="integration_imports_legacy_service",
                        importer=importer,
                        imported=imported,
                        suggestion="move the port/command contract to a domain or runtime public API",
                    )
                )

            if (
                importer.startswith("app.repositories.")
                or importer.startswith("app.cruds.")
                or ".graph_read.repository" in importer
            ) and (
                imported.startswith("app.services.")
                or ".use_case" in imported
                or ".use_cases." in imported
            ) and exception is None:
                errors.append(
                    _violation(
                        rule="persistence_imports_use_case",
                        importer=importer,
                        imported=imported,
                        suggestion="invert the dependency through a repository port",
                    )
                )

            if importer_domain:
                if imported.startswith("app.runtime."):
                    errors.append(
                        _violation(
                            rule="domain_imports_runtime",
                            importer=importer,
                            imported=imported,
                            suggestion="compose domain public APIs from runtime, not the reverse",
                            exception=exception,
                        )
                    )
                if is_legacy:
                    errors.append(
                        _violation(
                            rule="domain_imports_legacy_layer",
                            importer=importer,
                            imported=imported,
                            suggestion="use app.domains.<name>.public or an internal domain module",
                            exception=exception,
                        )
                    )
                if imported.startswith("app.domains."):
                    imported_domain = ".".join(imported.split(".")[:3])
                    if (
                        imported_domain != importer_domain
                        and imported != imported_domain + ".public"
                    ):
                        errors.append(
                            _violation(
                                rule="cross_domain_deep_import",
                                importer=importer,
                                imported=imported,
                                suggestion=f"import {imported_domain}.public",
                                exception=exception,
                            )
                        )

        if importer.startswith(("app.domains.", "app.runtime.")):
            for imported in item["external_imports"]:
                parts = importer.split(".")
                is_pure_domain_layer = len(parts) >= 4 and parts[3] in {
                    "application",
                    "domain",
                    "ports",
                }
                if is_pure_domain_layer and any(
                    _matches_prefix(imported, prefix)
                    for prefix in pure_layer_forbidden_prefixes
                ):
                    errors.append(
                        _violation(
                            rule="domain_pure_layer_imports_framework",
                            importer=importer,
                            imported=imported,
                            suggestion=(
                                "inject a port and keep framework code in api, "
                                "infrastructure, or integrations"
                            ),
                        )
                    )
                if any(
                    _matches_prefix(imported, prefix)
                    for prefix in provider_prefixes
                ):
                    errors.append(
                        _violation(
                            rule="domain_runtime_imports_provider_sdk",
                            importer=importer,
                            imported=imported,
                            suggestion="inject an app.integrations public adapter/port",
                        )
                    )

    graph = {
        module: {
            imported
            for imported in item["imports"]
            if imported in modules
        }
        for module, item in modules.items()
    }
    current_cycles = set(_strong_components(graph))
    for cycle, metadata in sorted(legacy_cycles.items()):
        if cycle not in current_cycles:
            errors.append(
                f"[stale_legacy_cycle] {' | '.join(cycle)}; "
                "allowed_fix=remove the obsolete cycle exception from policy; "
                f"owner_stage={metadata['owner_stage']}; "
                "docs=docs/architecture/backend-domains.md"
            )
    for cycle in sorted(current_cycles):
        if cycle not in legacy_cycles:
            errors.append(
                f"[module_cycle] {' | '.join(cycle)}; "
                "allowed_fix=break the cycle through a public API or port; "
                "legacy_exception=no; owner_stage=none; "
                "docs=docs/architecture/backend-domains.md"
            )

    area_graph: dict[str, set[str]] = {}
    for importer, imported in current_edges:
        importer_area = _area(importer)
        imported_area = _area(imported)
        if importer_area:
            area_graph.setdefault(importer_area, set())
        if imported_area:
            area_graph.setdefault(imported_area, set())
        if importer_area and imported_area and importer_area != imported_area:
            area_graph[importer_area].add(imported_area)
    for cycle in _strong_components(area_graph):
        errors.append(
            f"[package_cycle] {' | '.join(cycle)}; "
            "allowed_fix=depend only on another domain public API and remove the reverse edge; "
            "legacy_exception=no; owner_stage=none; "
            "docs=docs/architecture/backend-domains.md"
        )
    return sorted(set(errors))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        inventory = _load(args.inventory)
        policy = _load(args.policy)
        errors = check_inventory(inventory, policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Architecture boundary check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    exception_edges = sum(
        len(group["edges"]) for group in policy["legacy_exception_groups"]
    )
    print(
        "Architecture boundary check passed: "
        f"modules={inventory['module_count']} "
        f"edges={inventory['edge_count']} "
        f"legacy_exact_edges={exception_edges}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
