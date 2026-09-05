"""Additional role and direction checks for explicitly migrated scopes."""
from __future__ import annotations

import re
from datetime import date

ENTRY_ROLES = {"service", "schemas", "contracts"}
OLD_ROLES = {"api", "application", "domain", "infrastructure", "ports", "public"}
PURE_ROLES = {"policies", "utils", "exceptions"}
OLD_BACKEND_PREFIXES = {
    "app.services", "app.cruds", "app.repositories", "app.models", "app.schemas",
}
MODULE_NAME = re.compile(r"app(?:\.[a-z_][a-z0-9_]*)+")
BACKEND_BRIDGE_FIELDS = {
    "importer", "target", "owner_stage", "removal_condition", "reason", "review_date",
}


def validate_scope(policy: dict, *, frontend: bool) -> list[str]:
    fields = ("features", "common", "bridges") if frontend else (
        "domains", "globals", "modules", "entries", "bridges",
    )
    if not isinstance(policy, dict) or set(policy) - set(fields):
        return ["[refactor_invalid_scope] unknown scope fields"]
    for field in fields:
        values = policy.get(field, [])
        if not isinstance(values, list):
            return [f"[refactor_invalid_scope] {field} must be an array"]
        if field == "bridges":
            if not all(isinstance(value, dict) for value in values):
                return ["[refactor_invalid_scope] bridges must contain objects"]
            if not frontend:
                errors = validate_backend_bridge_shapes(values)
                if errors:
                    return errors
            continue
        if not all(isinstance(value, str) and value and "*" not in value and ".." not in value for value in values) or len(values) != len(set(values)):
            return [f"[refactor_invalid_scope] {field} requires unique exact names"]
        if field in {"features", "domains"} and any(not re.fullmatch(r"[a-z][a-z0-9_-]*", value) for value in values):
            return [f"[refactor_invalid_scope] invalid {field} name"]
        if field == "globals" and set(values) - {"app.config", "app.models", "app.exceptions", "app.pagination", "app.database"}:
            return ["[refactor_invalid_scope] globals must name approved foundation modules"]
        if field == "common" and any(not value.startswith(("components/", "lib/", "hooks/", "types/", "utils/", "styles/", "config/")) for value in values):
            return ["[refactor_invalid_scope] common must name exact common paths"]
        if field in {"modules", "entries"}:
            for value in values:
                owner, role = domain_role(value)
                if not MODULE_NAME.fullmatch(value) or not owner or not role or role in OLD_ROLES:
                    return [f"[refactor_invalid_scope] {field} must name exact new domain role modules"]
                if field == "modules" and owner in policy.get("domains", []):
                    return ["[refactor_invalid_scope] partial modules must not duplicate completed domains"]
                if field == "entries" and (role not in ENTRY_ROLES or not migrated_backend_module(value, policy)):
                    return ["[refactor_invalid_scope] entries must name migrated service/schema/contract modules"]
    return []


def domain_role(module: str) -> tuple[str | None, str | None]:
    parts = module.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "domains"]:
        return parts[2], parts[3] if len(parts) >= 4 else None
    return None, None


def migrated_backend_module(module: str, policy: dict) -> bool:
    """A partial module never implicitly opts in siblings or package descendants."""
    owner, role = domain_role(module)
    return (
        module in policy.get("modules", [])
        or module in policy.get("globals", [])
        or (owner in policy.get("domains", []) and role is not None and role not in OLD_ROLES)
    )


def validate_backend_bridge_shapes(bridges: list[dict]) -> list[str]:
    errors = []
    seen = set()
    for bridge in bridges:
        if set(bridge) != BACKEND_BRIDGE_FIELDS or not all(
            isinstance(bridge.get(field), str) and bridge[field].strip()
            for field in BACKEND_BRIDGE_FIELDS
        ):
            errors.append("[refactor_invalid_bridge] exact endpoints and ownership/removal/review metadata required")
            continue
        source, target = bridge["importer"], bridge["target"]
        pair = (source, target)
        if (not MODULE_NAME.fullmatch(source) or not MODULE_NAME.fullmatch(target)
                or source == target or pair in seen):
            errors.append(f"[refactor_invalid_bridge] {source} -> {target}")
        seen.add(pair)
        try:
            date.fromisoformat(bridge["review_date"])
        except ValueError:
            errors.append("[refactor_invalid_bridge] review_date must be an ISO date")
    return errors


def allowed_backend_entry(target: str, policy: dict) -> bool:
    owner, role = domain_role(target)
    return target in policy.get("entries", []) or (
        owner in policy.get("domains", []) and role in ENTRY_ROLES
        and target == f"app.domains.{owner}.{role}"
    )


def check_backend_edges(modules: dict, policy: dict) -> list[str]:
    moved = set(policy.get("domains", []))
    pure_globals = set(policy.get("globals", [])) & {"app.models", "app.exceptions", "app.pagination"}
    errors = []
    observed = {(source, target) for source, info in modules.items() for target in info["imports"]}
    bridges = {(bridge["importer"], bridge["target"]) for bridge in policy.get("bridges", [])}
    bridge_sources = {source for source, _ in bridges}
    for name in set(policy.get("modules", [])) | set(policy.get("entries", [])):
        if name not in modules:
            errors.append(f"[refactor_stale_scope] {name} is not an inventory module")
    for source, target in sorted(bridges):
        owner, role = domain_role(source)
        other, _ = domain_role(target)
        if source not in modules or target not in modules or (source, target) not in observed:
            errors.append(f"[refactor_stale_bridge] {source} -> {target}")
        if migrated_backend_module(source, policy) or (owner and role not in OLD_ROLES | {None}):
            errors.append(f"[refactor_invalid_bridge_source] {source} -> {target}")
        if not migrated_backend_module(target, policy):
            errors.append(f"[refactor_unmigrated_bridge_target] {source} -> {target}")
        if owner and owner != other:
            errors.append(f"[refactor_cross_domain_bridge] {source} -> {target}")
        if (target, source) in observed:
            errors.append(f"[refactor_reverse_bridge] {target} -> {source}")
    for source, info in modules.items():
        owner, role = domain_role(source)
        implementation = migrated_backend_module(source, policy)
        pure_implementation = role in PURE_ROLES or source in pure_globals - {"app.models"}
        horizontal_legacy = any(source == prefix or source.startswith(prefix + ".") for prefix in OLD_BACKEND_PREFIXES)
        for target in info["imports"]:
            other, target_role = domain_role(target)
            target_migrated = migrated_backend_module(target, policy)
            if owner and other and owner != other and (implementation or target_migrated or other in moved):
                if not (allowed_backend_entry(target, policy) or (other not in moved and target == f"app.domains.{other}.public")):
                    errors.append(f"[refactor_cross_domain_role] {source} -> {target}")
            if other and ((owner and owner == other) or horizontal_legacy) and target_migrated and not implementation and (source, target) not in bridges:
                errors.append(f"[refactor_unregistered_legacy_consumer] {source} -> {target}")
            if implementation:
                if ((owner and other == owner and target_role in OLD_ROLES)
                        or target in bridge_sources
                        or target.startswith(("app.services.", "app.cruds.", "app.repositories."))):
                    errors.append(f"[refactor_new_imports_legacy] {source} -> {target}")
                if owner and owner == other and target_role is not None and target_role not in OLD_ROLES and not target_migrated:
                    errors.append(f"[refactor_unmigrated_module_dependency] {source} -> {target}")
                if pure_implementation and (target_role in {"models", "repository", "router", "api"} or target in {"app.models", "app.database", "app.core.db"} or target.startswith(("app.models.", "app.runtime.", "app.integrations."))):
                    errors.append(f"[refactor_pure_imports_io] {source} -> {target}")
                if role in {"service", "repository"} and other == owner and target_role == "router":
                    errors.append(f"[refactor_service_imports_http] {source} -> {target}")
            if source in pure_globals and target.startswith(("app.domains.", "app.runtime.", "app.integrations.")):
                errors.append(f"[refactor_common_imports_application] {source} -> {target}")
        if implementation and pure_implementation:
            for target in info["external_imports"]:
                if target.split(".")[0] in {"fastapi", "starlette", "sqlalchemy", "sqlite3", "alembic", "httpx", "requests", "aiohttp", "boto3", "openai", "anthropic", "google", "redis", "neo4j", "kuzu"}:
                    errors.append(f"[refactor_pure_imports_framework] {source} -> {target}")
    return errors


def feature(path: str) -> str | None:
    parts = path.split("/")
    return parts[1] if len(parts) >= 2 and parts[0] == "features" else None


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    return bool(set(parts) & {"testing", "tests", "__tests__", "__mocks__"} or re.search(r"\.(test|spec)$", parts[-1]))


def check_frontend_edges(edges: list[tuple[str, str]], policy: dict) -> list[str]:
    moved = set(policy.get("features", []))
    common = set(policy.get("common", []))
    observed = set(edges)
    errors = []
    bridges = set()
    for bridge in policy.get("bridges", []):
        source, target = bridge.get("importer"), bridge.get("target")
        if not all(isinstance(bridge.get(k), str) and bridge[k].strip() for k in ("importer", "target", "owner_stage", "removal_condition")):
            errors.append("[refactor_invalid_bridge] missing metadata")
            continue
        pair = (source, target)
        if pair in bridges or source == target or any("*" in part for part in pair):
            errors.append(f"[refactor_invalid_bridge] {source} -> {target}")
        bridges.add(pair)
        if pair not in observed:
            errors.append(f"[refactor_stale_bridge] {source} -> {target}")
        if (target, source) in observed:
            errors.append(f"[refactor_reverse_bridge] {target} -> {source}")
        if target not in common and feature(target) not in moved:
            errors.append(f"[refactor_unmigrated_bridge_target] {source} -> {target}")
    for source, target in observed:
        owner, other = feature(source), feature(target)
        if owner and other in moved and owner != other and (source, target) not in bridges:
            errors.append(f"[refactor_unregistered_legacy_consumer] {source} -> {target}")
        if source.startswith(("app/", "composition/")) and other in moved and target.endswith("/public"):
            errors.append(f"[refactor_composition_imports_legacy_entry] {source} -> {target}")
        if not is_test_path(source) and is_test_path(target):
            errors.append(f"[refactor_production_imports_test] {source} -> {target}")
        if owner in moved:
            if other is not None and other != owner:
                errors.append(f"[refactor_cross_feature] {source} -> {target}")
            if target.startswith(("app/", "composition/")):
                errors.append(f"[refactor_feature_imports_composition] {source} -> {target}")
        if source in common and target.startswith(("features/", "app/", "composition/")):
            errors.append(f"[refactor_common_imports_application] {source} -> {target}")
        if owner in moved or source in common:
            if target.startswith("shared/") or target in {a for a, _ in bridges}:
                errors.append(f"[refactor_new_imports_legacy] {source} -> {target}")
    graph: dict[str, set[str]] = {}
    for source, target in observed:
        graph.setdefault(source, set()).add(target)
    visited, active = set(), []

    def visit(node: str) -> None:
        if node in active:
            cycle = active[active.index(node):]
            if any(member in common or feature(member) in moved for member in cycle):
                errors.append("[refactor_module_cycle] " + " -> ".join(cycle + [node]))
            return
        if node in visited:
            return
        visited.add(node)
        active.append(node)
        for target in sorted(graph.get(node, [])):
            visit(target)
        active.pop()

    if moved or common:
        for node in sorted(graph):
            visit(node)
    return sorted(set(errors))
