"""Generate the deterministic pre-refactor internal import baseline for T2.5."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "backend/app"
DEFAULT_OUTPUT = ROOT / "security/architecture_import_baseline.json"


def _module(path: Path) -> str:
    relative = path.relative_to(ROOT / "backend").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _internal_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name == "app" or alias.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level == 0 and (node.module == "app" or node.module.startswith("app.")):
                imports.add(node.module)
    return sorted(imports)


def render() -> str:
    modules = [
        {"module": _module(path), "imports": _internal_imports(path)}
        for path in sorted(APP_ROOT.rglob("*.py"))
    ]
    edges = sum(len(item["imports"]) for item in modules)
    payload = {
        "schema_version": 1,
        "purpose": "T2.5 pre-refactor internal app import baseline",
        "root": "backend/app",
        "module_count": len(modules),
        "edge_count": edges,
        "modules": modules,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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
        f"modules={payload['module_count']} edges={payload['edge_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
