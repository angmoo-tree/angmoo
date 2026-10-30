"""Map reviewed World erasure policies to their actual frozen runtime paths."""
import argparse
import ast
import json
from pathlib import Path
import re


def resource_arguments(backend_root: Path) -> list[str]:
    root = backend_root.resolve()
    inventory = root / "app/runtime/persistence/world_erasure_inventory.py"
    tree = ast.parse(inventory.read_text(encoding="utf-8"))
    owners = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                 and target.id == "OWNERS" for target in node.targets))
    if not isinstance(owners, tuple) or not owners or len(set(owners)) != len(owners):
        raise ValueError("world_erasure_resource_owners_invalid")
    arguments = []
    for owner in owners:
        if not isinstance(owner, str) or re.fullmatch(r"[a-z][a-z_]{0,63}", owner) is None:
            raise ValueError("world_erasure_resource_owner_invalid")
        source = root / "app/domains" / owner / "repository/world_erasure.json"
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("world_erasure_resource_path_invalid")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("owner") != owner or payload.get("version") != 1 or not isinstance(payload.get("tables"), dict):
            raise ValueError("world_erasure_resource_contract_invalid")
        arguments.extend(("--add-data", f"{source};app/domains/{owner}/repository"))
    return arguments


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-root", required=True, type=Path)
    print(json.dumps(resource_arguments(parser.parse_args().backend_root)))
