"""Generate or verify the public route-security inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
PRIVATE_INVENTORY = BACKEND_ROOT / "security" / "route_security_inventory.json"
PUBLIC_INVENTORY = BACKEND_ROOT / "security" / "public_route_security_inventory.json"
sys.path.insert(0, str(BACKEND_ROOT))

from app.public_main import app  # noqa: E402


def render_inventory(private_path: Path = PRIVATE_INVENTORY) -> str:
    private = json.loads(private_path.read_text(encoding="utf-8"))
    private_routes = private["routes"]
    schema = app.openapi()
    public_keys = sorted(
        f"{method.upper()} {path}"
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method.lower()
        in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    )
    missing = sorted(set(public_keys) - set(private_routes))
    if missing:
        raise RuntimeError(
            "public operations are missing from private inventory: " + ", ".join(missing)
        )
    payload = {
        "schema_version": 1,
        "profile": "public",
        "routes": {key: private_routes[key] for key in public_keys},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=PUBLIC_INVENTORY)
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("use --write or --check")

    try:
        rendered = render_inventory()
        output = args.output.resolve()
        if args.write:
            output.write_text(rendered, encoding="utf-8", newline="\n")
        if args.check and output.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("public route inventory is stale")
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"Public route inventory failed: {exc}", file=sys.stderr)
        return 1
    print(f"Public route inventory passed: operations={len(json.loads(rendered)['routes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
