"""Exact, reviewed product changes layered over immutable refactor evidence.

This is not a replacement checkpoint. Each entry names a committed product
change, its reason, and exact before/after contract fragments. Unlisted drift
still fails the original preservation checker.
"""
from __future__ import annotations

from collections import Counter
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess

MANIFEST = "security/post_refactor_contract_changes.json"


def load(root: Path) -> list[dict]:
    path = root / MANIFEST
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("records"), list):
        raise ValueError("invalid post-refactor change manifest")
    records = payload["records"]
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=root)
    for commit in git("log", "--format=%H", "--", MANIFEST).decode().splitlines():
        old = json.loads(git("show", f"{commit}:{MANIFEST}"))["records"]
        if records[:len(old)] != old:
            raise ValueError("post-refactor change history must be append-only")
    seen = set()
    for record in records:
        commit = record.get("implementation_commit", "")
        if (not re.fullmatch(r"[0-9a-f]{40}", commit)
                or not record.get("reason") or not record.get("review")
                or not record.get("id") or record["id"] in seen):
            raise ValueError("product change requires unique ID, commit, reason and review")
        seen.add(record["id"])
        git("merge-base", "--is-ancestor", commit, "HEAD")
        if not record.get("source_blobs"):
            raise ValueError("product change requires committed source evidence")
        for source, blob in record["source_blobs"].items():
            if git("rev-parse", f"{commit}:{source}").decode().strip() != blob:
                raise ValueError("product change source provenance differs")
        for removed in record.get("removed_bindings", []):
            source, symbol = removed["source"], removed["symbol"]
            if source not in record["source_blobs"] or not re.fullmatch(r"[A-Za-z_]\w*", symbol):
                raise ValueError("removed binding requires exact committed source evidence")
            before = git("show", f"{commit}^:{source}").decode("utf-8-sig")
            after = git("show", f"{commit}:{source}").decode("utf-8-sig")
            def definitions(text: str) -> list[str]:
                return [ast.dump(node, include_attributes=False) for node in ast.parse(text).body
                        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol)
                        or (isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                            isinstance(target, ast.Name) and target.id == symbol
                            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])))]
            if definitions(before) != [removed["before_ast"]] or definitions(after) or definitions((root / source).read_text(encoding="utf-8-sig")):
                raise ValueError("removed binding preimage or actual absence differs")
    return records


def removed_bindings(records: list[dict]) -> set[tuple[str, str]]:
    return {(item["source"], item["symbol"]) for record in records for item in record.get("removed_bindings", [])}


def contracts(original: dict, records: list[dict]) -> dict:
    result = deepcopy(original)
    for record in records:
        seen = set()
        for change in record.get("contracts", []):
            app, kind, key = (change[name] for name in ("application", "kind", "key"))
            if app not in {"full", "public"} or kind not in {"operations", "schemas"}:
                raise ValueError("product change cannot alter ORM or unknown contract categories")
            identity = (app, kind, key)
            if identity in seen or change["before"] == change["after"]:
                raise ValueError("duplicate or empty product contract change")
            seen.add(identity)
            target = result[app][kind]
            if target.get(key) != change["before"]:
                raise ValueError(f"product contract preimage differs: {identity}")
            if change["after"] is None:
                target.pop(key)
            else:
                target[key] = change["after"]
    return result


def assertions(node: str, required: Counter, found: Counter, records: list[dict]) -> Counter:
    for record in records:
        for change in record.get("assertions", []):
            if change["node"] != node:
                continue
            before, after = Counter(change["before"]), Counter(change["after"])
            # Later introduction evidence already contains the approved version.
            if required == after:
                continue
            if required != before or found != after:
                raise ValueError(f"product assertion before/after differs: {node}")
            required = after
    return required
