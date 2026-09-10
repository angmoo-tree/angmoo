"""Exact, reviewed product changes layered over immutable refactor evidence.

This is not a replacement checkpoint. Each entry names a committed product
change, its reason, and exact before/after contract fragments. Unlisted drift
still fails the original preservation checker.
"""
from __future__ import annotations

from collections import Counter
import ast
from copy import deepcopy
from functools import lru_cache
import json
import hashlib
from pathlib import Path
import re
import subprocess

MANIFEST = "security/post_refactor_contract_changes.json"


def load(root: Path, *, reader=None) -> list[dict]:
    path = root / MANIFEST
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("records"), list):
        raise ValueError("invalid post-refactor change manifest")
    records = payload["records"]
    def git(*args: str) -> bytes:
        return reader(*args, root=root) if reader is not None else subprocess.check_output(["git", *args], cwd=root)
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
        for change in record.get("definitions", []):
            source, symbol = change["source"], change["symbol"]
            if source not in record["source_blobs"] or change["before_ast"] == change["after_ast"]:
                raise ValueError("definition change requires committed source evidence")
            for revision, field in ((commit + "^", "before_ast"), (commit, "after_ast")):
                if definition_ast(git("show", f"{revision}:{source}").decode("utf-8-sig"), symbol) != normalize_ast_dump(change[field]):
                    raise ValueError("definition change committed preimage differs")
        for change in record.get("frontend_files", []):
            source = change["source"]
            if (source not in record["source_blobs"]
                    or not source.startswith(("frontend/", "browser-tests/"))
                    or change["before_sha256"] == change["after_sha256"]):
                raise ValueError("frontend change requires committed source evidence")
            for revision, field in ((commit + "^", "before_sha256"), (commit, "after_sha256")):
                if text_digest(git("show", f"{revision}:{source}").decode("utf-8")) != change[field]:
                    raise ValueError("frontend change committed preimage differs")
        if record.get("orm_tables"):
            migrations = record.get("migration_sources", [])
            if not migrations or any(path not in record["source_blobs"] for path in migrations):
                raise ValueError("ORM change requires committed migration evidence")
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


def text_digest(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def frontend_matches(source: str, original: str, actual: str, records: list[dict]) -> bool:
    """Apply only a continuous, committed, exact file delta; no broad exemption."""
    expected = text_digest(original)
    for record in records:
        for change in record.get("frontend_files", []):
            if change["source"] == source:
                if expected != change["before_sha256"]:
                    raise ValueError("frontend change chain preimage differs")
                expected = change["after_sha256"]
    return expected == text_digest(actual)


@lru_cache(maxsize=128)
def definition_ast(source: str, symbol: str) -> str:
    body = ast.parse(source).body
    for part in symbol.split("."):
        found = [node for node in body if getattr(node, "name", None) == part or
                 isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                     isinstance(target, ast.Name) and target.id == part for target in
                     (node.targets if isinstance(node, ast.Assign) else [node.target]))]
        if len(found) != 1:
            raise ValueError("definition change must name one exact symbol")
        node = found[0]
        body = getattr(node, "body", [])
    return ast.dump(node, include_attributes=False)


@lru_cache(maxsize=128)
def normalize_ast_dump(value: str) -> str:
    """Normalize AST dumps or captured assertion source without executing text."""
    if not re.match(r"[A-Z][A-Za-z_0-9]*\(", value):
        parsed = ast.parse(value)
        if len(parsed.body) == 1:
            statement = parsed.body[0]
            assertion_context = (isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and statement.value.func.attr in {"raises", "warns"})
            if isinstance(statement, ast.Assert) or assertion_context:
                return ast.dump(parsed, include_attributes=False)
        return value

    def decode(node):
        if isinstance(node, ast.Name) and node.id == "Ellipsis":
            return Ellipsis
        if isinstance(node, ast.Call):
            constructor = getattr(ast, node.func.id, None) if isinstance(node.func, ast.Name) else None
            if not isinstance(constructor, type) or not issubclass(constructor, ast.AST) or any(key.arg is None for key in node.keywords):
                raise ValueError("invalid AST evidence constructor")
            return constructor(*[decode(arg) for arg in node.args], **{key.arg: decode(key.value) for key in node.keywords})
        if isinstance(node, ast.List):
            return [decode(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(decode(item) for item in node.elts)
        return ast.literal_eval(node)

    result = decode(ast.parse(value, mode="eval").body)
    if not isinstance(result, ast.AST):
        raise ValueError("invalid AST evidence root")
    return ast.dump(result, include_attributes=False)


def definition_matches(root: Path, source: str, symbol: str, before: ast.AST, after: ast.AST, *, records=None) -> bool:
    expected = ast.dump(before, include_attributes=False)
    actual = ast.dump(after, include_attributes=False)
    if expected == actual:
        return True
    for record in load(root) if records is None else records:
        for change in record.get("definitions", []):
            if ((change["source"], change["symbol"]) == (source, symbol)
                    and normalize_ast_dump(change["before_ast"]) == expected):
                expected = normalize_ast_dump(change["after_ast"])
    return expected == actual


def removed_bindings(records: list[dict]) -> set[tuple[str, str]]:
    return {(item["source"], item["symbol"]) for record in records for item in record.get("removed_bindings", [])}


def contracts(original: dict, records: list[dict]) -> dict:
    result = deepcopy(original)
    for record in records:
        for change in record.get("orm_tables", []):
            if result["orm_tables"].get(change["key"]) != change["before"] or change["before"] == change["after"]:
                raise ValueError("product ORM preimage differs")
            result["orm_tables"][change["key"]] = change["after"]
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
    transitions = []
    for record in records:
        for change in record.get("assertions", []):
            if change["node"] != node:
                continue
            before = Counter(normalize_ast_dump(value) for value in change["before"])
            after = Counter(normalize_ast_dump(value) for value in change["after"])
            if transitions and transitions[-1][1] != before:
                raise ValueError(f"product assertion before/after differs: {node}")
            transitions.append((before, after))
    if not transitions:
        return required
    # A later introduction snapshot may already contain the final reviewed state.
    states = [transitions[0][0], *(after for _, after in transitions)]
    if required not in states:
        raise ValueError(f"product assertion before/after differs: {node}")
    final = states[-1]
    if required != final and found != final:
        raise ValueError(f"product assertion before/after differs: {node}")
    return final
