"""Enforce the L2.5 frontend product-shell public boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "security/frontend_architecture_policy.json"
DEFAULT_SOURCE_ROOT = ROOT / "frontend/src"
IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]"
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: root must be an object")
    return payload


def _relative(path: Path, source_root: Path) -> str:
    return path.relative_to(source_root.parent.parent).as_posix()


def _imports(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return sorted(set(IMPORT_PATTERN.findall(text)))


def _feature_for_path(path: Path, source_root: Path) -> str | None:
    try:
        relative = path.relative_to(source_root / "features")
    except ValueError:
        return None
    return relative.parts[0] if relative.parts else None


def _feature_for_import(target: str) -> tuple[str, str] | None:
    prefix = "@/features/"
    if not target.startswith(prefix):
        return None
    remainder = target[len(prefix) :]
    feature, separator, suffix = remainder.partition("/")
    return feature, suffix if separator else ""


def _validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("policy.schema_version must be 1")
    if policy.get("policy_id") != "angmoo-l2-5-frontend-product-shell-v1":
        errors.append("policy.policy_id must be angmoo-l2-5-frontend-product-shell-v1")
    if policy.get("documentation") != "docs/architecture/frontend-product-shell.md":
        errors.append("policy.documentation must point to the frontend shell map")
    for field in ("feature_names", "legacy_import_prefixes", "required_paths"):
        values = policy.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            errors.append(f"policy.{field} must be a string array")
        elif values != sorted(set(values)):
            errors.append(f"policy.{field} must be sorted and unique")
    markers = policy.get("required_markers")
    if not isinstance(markers, dict):
        errors.append("policy.required_markers must be an object")
    else:
        for path, values in markers.items():
            if not isinstance(path, str) or not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                errors.append("policy.required_markers values must be string arrays")
            elif values != sorted(set(values)):
                errors.append(f"policy.required_markers[{path}] must be sorted and unique")
    exceptions = policy.get("legacy_import_exceptions")
    if not isinstance(exceptions, list):
        errors.append("policy.legacy_import_exceptions must be an array")
    else:
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(exceptions):
            label = f"policy.legacy_import_exceptions[{index}]"
            if not isinstance(item, dict) or set(item) != {
                "importer",
                "target",
                "owner_stage",
                "removal_condition",
            }:
                errors.append(
                    f"{label} must contain importer, target, owner_stage, and removal_condition"
                )
                continue
            if not all(isinstance(value, str) and value for value in item.values()):
                errors.append(f"{label} values must be non-empty strings")
                continue
            key = (item["importer"], item["target"])
            if key in seen:
                errors.append(f"{label} duplicates {key[0]} -> {key[1]}")
            seen.add(key)
    return errors


def check_frontend(source_root: Path, policy: dict[str, Any]) -> list[str]:
    errors = _validate_policy(policy)
    if errors:
        return sorted(errors)

    repository_root = source_root.parent.parent
    documentation = policy["documentation"]
    for relative in policy["required_paths"]:
        if not (repository_root / relative).is_file():
            errors.append(
                f"[missing_public_boundary] {relative}; docs={documentation}"
            )
    for relative, markers in policy["required_markers"].items():
        path = repository_root / relative
        if not path.is_file():
            errors.append(f"[missing_contract_file] {relative}; docs={documentation}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(
                    f"[missing_contract_marker] {relative}: {marker}; docs={documentation}"
                )

    exceptions = {
        (item["importer"], item["target"]): item
        for item in policy["legacy_import_exceptions"]
    }
    observed_exceptions: set[tuple[str, str]] = set()
    legacy_prefixes = tuple(policy["legacy_import_prefixes"])
    feature_names = set(policy["feature_names"])

    source_files = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx"}
    )
    for path in source_files:
        relative = _relative(path, source_root)
        importer_feature = _feature_for_path(path, source_root)
        is_route_root = path.name in {"layout.tsx", "page.tsx"} and (
            source_root / "app" in path.parents
        )
        is_shared = source_root / "shared" in path.parents

        for target in _imports(path):
            target_feature = _feature_for_import(target)
            if target_feature:
                feature, suffix = target_feature
                if feature not in feature_names:
                    errors.append(
                        f"[unknown_feature_import] {relative} -> {target}; docs={documentation}"
                    )
                if is_route_root and suffix != "public":
                    errors.append(
                        f"[route_deep_feature_import] {relative} -> {target}; "
                        f"allowed_fix=@/features/{feature}/public; docs={documentation}"
                    )
                if importer_feature and feature != importer_feature and suffix != "public":
                    errors.append(
                        f"[cross_feature_deep_import] {relative} -> {target}; "
                        f"allowed_fix=@/features/{feature}/public; docs={documentation}"
                    )
                if is_shared:
                    errors.append(
                        f"[shared_imports_feature] {relative} -> {target}; "
                        f"allowed_fix=move product policy to a feature; docs={documentation}"
                    )

            if importer_feature and target.startswith(legacy_prefixes):
                key = (relative, target)
                if key in exceptions:
                    observed_exceptions.add(key)
                else:
                    errors.append(
                        f"[feature_imports_legacy_layer] {relative} -> {target}; "
                        "allowed_fix=move the typed contract behind the feature public boundary; "
                        f"docs={documentation}"
                    )

            if is_shared and target.startswith(("@/app", "@/components", "@/lib")):
                errors.append(
                    f"[shared_imports_product_layer] {relative} -> {target}; "
                    "allowed_fix=keep shared primitives product-neutral; "
                    f"docs={documentation}"
                )

    for key, item in sorted(exceptions.items()):
        if key not in observed_exceptions:
            errors.append(
                f"[stale_frontend_exception] {key[0]} -> {key[1]}; "
                f"owner_stage={item['owner_stage']}; docs={documentation}"
            )
    return sorted(set(errors))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        policy = _load(args.policy)
        errors = check_frontend(args.source_root, policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Frontend architecture boundary check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(
        "Frontend architecture boundary check passed: "
        f"features={len(policy['feature_names'])} "
        f"legacy_exact_edges={len(policy['legacy_import_exceptions'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
