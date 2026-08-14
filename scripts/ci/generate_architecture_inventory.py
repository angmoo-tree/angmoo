"""Generate the deterministic internal import inventory for T2.5."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "backend/app"
DEFAULT_OUTPUT = ROOT / "security/architecture_import_baseline.json"


def _module(path: Path, *, root: Path = ROOT) -> str:
    relative = path.relative_to(root / "backend").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_paths(*, root: Path = ROOT) -> dict[str, Path]:
    app_root = root / "backend/app"
    return {
        _module(path, root=root): path
        for path in sorted(app_root.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def _resolve_relative_module(
    *,
    current_module: str,
    is_package: bool,
    level: int,
    module: str | None,
) -> str:
    package = current_module if is_package else current_module.rpartition(".")[0]
    parts = package.split(".") if package else []
    climb = level - 1
    if climb > len(parts):
        return ""
    base_parts = parts[: len(parts) - climb]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _best_known_target(name: str, known_modules: set[str]) -> str | None:
    candidate = name
    while candidate == "app" or candidate.startswith("app."):
        if candidate in known_modules:
            return candidate
        if "." not in candidate:
            break
        candidate = candidate.rpartition(".")[0]
    return None


def _imports(
    path: Path,
    *,
    current_module: str,
    known_modules: set[str],
) -> tuple[list[str], list[str], list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    internal: set[str] = set()
    external: set[str] = set()
    wildcard: set[str] = set()
    is_package = path.name == "__init__.py"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    target = _best_known_target(alias.name, known_modules)
                    if target:
                        internal.add(target)
                else:
                    external.add(alias.name)
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            base = _resolve_relative_module(
                current_module=current_module,
                is_package=is_package,
                level=node.level,
                module=node.module,
            )
        else:
            base = node.module or ""

        if base == "app" or base.startswith("app."):
            for alias in node.names:
                if alias.name == "*":
                    wildcard.add(base)
                    target = _best_known_target(base, known_modules)
                else:
                    target = _best_known_target(
                        f"{base}.{alias.name}" if base else alias.name,
                        known_modules,
                    )
                    if target is None:
                        target = _best_known_target(base, known_modules)
                if target:
                    internal.add(target)
        elif base:
            external.add(base)
            if any(alias.name == "*" for alias in node.names):
                wildcard.add(base)

    return sorted(internal), sorted(external), sorted(wildcard)


def build_inventory(*, root: Path = ROOT) -> dict[str, Any]:
    module_paths = _module_paths(root=root)
    known_modules = set(module_paths)
    modules: list[dict[str, Any]] = []
    for module, path in sorted(module_paths.items()):
        internal, external, wildcard = _imports(
            path,
            current_module=module,
            known_modules=known_modules,
        )
        modules.append(
            {
                "external_imports": external,
                "imports": internal,
                "module": module,
                "path": path.relative_to(root).as_posix(),
                "wildcard_imports": wildcard,
            }
        )
    return {
        "edge_count": sum(len(item["imports"]) for item in modules),
        "external_import_count": sum(
            len(item["external_imports"]) for item in modules
        ),
        "module_count": len(modules),
        "modules": modules,
        "purpose": "T2.5 deterministic internal app import inventory",
        "root": "backend/app",
        "schema_version": 2,
    }


def render(*, root: Path = ROOT) -> str:
    return json.dumps(
        build_inventory(root=root),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("use --write or --check")
    try:
        rendered = render()
        if args.write:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        if args.check and args.output.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("architecture import baseline is stale")
    except (OSError, SyntaxError, RuntimeError) as exc:
        print(f"Architecture inventory failed: {exc}", file=sys.stderr)
        return 1
    payload = json.loads(rendered)
    print(
        "Architecture inventory passed: "
        f"modules={payload['module_count']} "
        f"internal_edges={payload['edge_count']} "
        f"external_imports={payload['external_import_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
