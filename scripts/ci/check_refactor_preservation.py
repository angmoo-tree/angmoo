"""Compare the current refactor against its frozen source and behavior baseline.

The baseline is historical evidence, never a snapshot to regenerate after a move.
Test renames are explicit and one-to-one; additional tests remain welcome.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "security/refactor_source_baseline.json"
INVENTORY = ROOT / "security/refactor_feature_inventory.json"
MOVES = ROOT / "security/refactor_path_map.json"
CHECKPOINT = ROOT / "security/refactor_backend_checkpoint.json"
ADDITIONS = ROOT / "security/refactor_backend_additions.json"
CHECKPOINT_COMMIT = "d7037625a19071eb279ad2ea35c3ace6fe5b5289"
# These anchors identify historical evidence. A candidate tree must not replace
# either document with its own source/test collection to make a move pass.
CHECKPOINT_DIGEST = "264aaf30d2534b8b7799a262edf6ff25055a0cfbf900cbb2bb8b11fcb8dd963b"
BASELINE_BLOB = "bad10d7384accf86c96bfddca40de676c425fcae"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def current_contracts() -> dict:
    # Import without lifespan: no DB initialization, scheduler, or provider call.
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app as full_app
    from app.public_main import app as public_app
    import app.models  # noqa: F401 - canonical model registration
    from app.core.db import Base

    contracts = {}
    for name, application in (("full", full_app), ("public", public_app)):
        schema = application.openapi()
        contracts[name] = {
            "operations": {f"{method.upper()} {path}": digest(operation)
                           for path, methods in sorted(schema["paths"].items())
                           for method, operation in sorted(methods.items())},
            "schemas": {name: digest(value) for name, value in sorted(schema.get("components", {}).get("schemas", {}).items())},
        }
    contracts["orm_tables"] = {
        name: digest({
            "columns": [{"name": col.name, "type": str(col.type), "nullable": col.nullable,
                         "primary_key": col.primary_key,
                         "foreign_keys": sorted(fk.target_fullname for fk in col.foreign_keys)}
                        for col in table.columns],
            "indexes": sorted((idx.name or "", idx.unique, sorted(col.name for col in idx.columns)) for idx in table.indexes),
        }) for name, table in sorted(Base.metadata.tables.items())
    }
    return contracts


def mapped_targets(approved: list[str], moves: dict[str, str], *, nodes: bool = False,
                   node_snapshots: list[list[str]] | None = None) -> dict[str, str]:
    """Follow successive moves, including roots already present at a checkpoint.

    A -> B -> C is one lineage. A -> C and B -> C would erase an independent
    test and is prohibited. Unreachable origins are typos, not implicit approval.
    """
    if not isinstance(moves, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in moves.items()):
        raise ValueError("moves must contain nonempty exact string paths/nodes")
    if nodes and len(set(moves.values())) != len(moves):
        raise ValueError("test node moves must be one-to-one")
    used, targets = set(), {}
    for origin in approved:
        target, seen = origin, set()
        while target in moves:
            if target in seen:
                raise ValueError(f"cyclic {'test node' if nodes else 'source'} move: {origin}")
            seen.add(target)
            used.add(target)
            target = moves[target]
        targets[origin] = target
    unknown = set(moves) - used
    if unknown:
        raise ValueError(f"moves absent from frozen baseline/checkpoint/additions: {sorted(unknown)}")
    if nodes:
        for snapshot in node_snapshots if node_snapshots is not None else [approved]:
            destinations = [targets[node] for node in snapshot]
            if len(set(destinations)) != len(destinations):
                raise ValueError("test node moves must be one-to-one within each frozen snapshot; independent cases cannot collapse")
    return targets


def missing_nodes(approved: list[str], current: list[str], moves: dict[str, str], *,
                  node_snapshots: list[list[str]] | None = None) -> list[str]:
    targets = mapped_targets(approved, moves, nodes=True, node_snapshots=node_snapshots)
    return sorted(set(targets.values()) - set(current))


def git_bytes(*args: str, root: Path = ROOT) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode:
        raise ValueError("git evidence unavailable; fetch full history: " + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def checkpoint_errors(checkpoint: dict, baseline_bytes: bytes) -> list[str]:
    errors = []
    if digest(checkpoint) != CHECKPOINT_DIGEST:
        errors.append("backend checkpoint mutated; restore the frozen AR-G0 evidence, do not regenerate it")
    if checkpoint.get("commit") != CHECKPOINT_COMMIT:
        errors.append("backend checkpoint must reference the exact PR263 commit")
    # Git content uses LF, independent of a Windows checkout's autocrlf setting.
    if git_blob(baseline_bytes.replace(b"\r\n", b"\n")) != BASELINE_BLOB:
        errors.append("PR258 source baseline mutated")
    return errors


def assertion_contracts(source: str) -> dict[str, list[str]]:
    """Record assertions and exception expectations, without positional trivia.

    Additional assertions are welcome. This complements execution and review;
    node presence alone never proves that an assertion still checks behavior.
    """
    tree = ast.parse(source)
    contracts = {}

    def visit(body: list[ast.stmt], parents: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*parents, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fragments = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Assert):
                        fragments.append(ast.unparse(child))
                    elif isinstance(child, (ast.With, ast.AsyncWith)):
                        for item in child.items:
                            call = item.context_expr
                            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in {"raises", "warns"}:
                                fragments.append(ast.unparse(call))
                contracts["::".join((*parents, node.name))] = fragments

    visit(tree.body)
    return contracts


def suppression_contracts(source: str) -> dict[str, list[str]]:
    """Freeze skip/xfail/warning suppressions at their lexical scope."""
    contracts = {"<module>": []}
    suppressed = {"skip", "skipif", "xfail", "skipIf", "skipUnless", "expectedFailure"}

    def visit(node: ast.AST, scope: str = "<module>") -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = node.name if scope == "<module>" else f"{scope}::{node.name}"
            contracts.setdefault(scope, [])
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
            if name in suppressed:
                contracts.setdefault(scope, []).append(ast.unparse(node))
                return
        if isinstance(node, ast.Attribute) and node.attr in suppressed:
            contracts.setdefault(scope, []).append(ast.unparse(node))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(ast.parse(source))
    return {scope: values for scope, values in contracts.items() if values}


def node_function(node: str) -> tuple[str, str]:
    path, _, function = node.partition("::")
    return path, function.split("[", 1)[0]


def path_literals(files: dict[str, str]) -> list[tuple[str, str]]:
    """Only explicit file/module paths may change in preserved assertions."""
    pairs = []
    for old, new in files.items():
        if old == new:
            continue
        pairs.append((old, new))
        if old.startswith("backend/") and new.startswith("backend/"):
            pairs.append((old.removeprefix("backend/"), new.removeprefix("backend/")))
        if old.startswith("backend/app/") and new.startswith("backend/app/") and old.endswith(".py") and new.endswith(".py"):
            pairs.append((old.removeprefix("backend/")[:-3].replace("/", "."), new.removeprefix("backend/")[:-3].replace("/", ".")))
    return sorted(pairs, key=lambda pair: -len(pair[0]))


def _scope_binding_counts(body: list[ast.stmt]) -> Counter:
    """Include non-Name binding syntax without entering another lexical scope."""
    counts = Counter()
    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            counts[node.name] += 1
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                counts[alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)] += 1
            return
        if isinstance(node, ast.ExceptHandler) and node.name:
            counts[node.name] += 1
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            counts[node.name] += 1
        if isinstance(node, ast.MatchMapping) and node.rest:
            counts[node.rest] += 1
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            counts[node.id] += 1
        for child in ast.iter_child_nodes(node):
            visit(child)
    for item in body:
        visit(item)
    return counts


def literal_path_roots(source: str, source_path: str) -> dict[str, dict[str, str]]:
    """Resolve only single-assignment, literal paths anchored to this test file.

    No filesystem calls or evaluated Python enter the comparison. Unsupported
    expressions, shadowed names and reassignments cannot authorize a path move.
    """
    tree = ast.parse(source)
    path_imported = any(isinstance(n, ast.ImportFrom) and n.module == "pathlib"
                        and any(a.name == "Path" and a.asname is None for a in n.names)
                        for n in tree.body)
    module_bindings = _scope_binding_counts(tree.body)
    if not path_imported or module_bindings["Path"] != 1 or module_bindings["__file__"] or module_bindings["*"]:
        return {}

    def resolve(node: ast.AST, env: dict[str, PurePosixPath]):
        if isinstance(node, ast.Name):
            return env.get(node.id)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Path" and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__"):
            return PurePosixPath(source_path)
        if isinstance(node, ast.Call) and not node.args and not node.keywords and isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
            return resolve(node.func.value, env)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            value = resolve(node.value, env)
            return value.parent if value is not None else None
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                and node.value.attr == "parents" and isinstance(node.slice, ast.Constant)
                and type(node.slice.value) is int and node.slice.value >= 0):
            value = resolve(node.value.value, env)
            if value is not None and node.slice.value < len(value.parents):
                return value.parents[node.slice.value]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant):
            value, segment = resolve(node.left, env), node.right.value
            if value is not None and isinstance(segment, str) and segment not in {"", ".", ".."} and "/" not in segment and "\\" not in segment:
                return value / segment
        return None

    def bindings(body: list[ast.stmt], inherited: dict[str, PurePosixPath], parameters=()):
        stores = _scope_binding_counts(body)
        env = {name: value for name, value in inherited.items() if name not in stores and name not in parameters}
        for item in body:
            targets = item.targets if isinstance(item, ast.Assign) else [item.target] if isinstance(item, ast.AnnAssign) else []
            if len(targets) != 1 or not isinstance(targets[0], ast.Name) or stores[targets[0].id] != 1:
                continue
            name = targets[0].id
            value = resolve(item.value, env) if item.value is not None else None
            if value is not None:
                env[name] = value
        return env

    global_env = bindings(tree.body, {})
    result = {}

    def visit(body, parents=()):
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*parents, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
                params.update(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
                local_stores = set(_scope_binding_counts(node.body))
                if (params | local_stores) & {"Path", "__file__", "*"}:
                    continue
                result["::".join((*parents, node.name))] = {
                    name: value.as_posix() for name, value in bindings(node.body, global_env, params).items()
                }
    visit(tree.body)
    return result


def normalized_assertion(fragment: str, literals: list[tuple[str, str]], *, roots: dict[str, str] | None = None) -> str:
    roots = roots or {}
    exact_paths = {old: new for old, new in literals if old.startswith("backend/") and new.startswith("backend/")}
    destinations = set(exact_paths.values())

    class Paths(ast.NodeTransformer):
        def visit_BinOp(self, node):
            if not isinstance(node.op, ast.Div):
                return self.generic_visit(node)
            segments, base = [], node
            while isinstance(base, ast.BinOp) and isinstance(base.op, ast.Div):
                if not isinstance(base.right, ast.Constant) or not isinstance(base.right.value, str):
                    return node
                segment = base.right.value
                if segment in {"", ".", ".."} or "/" in segment or "\\" in segment:
                    return node
                segments.append(segment)
                base = base.left
            if not isinstance(base, ast.Name) or base.id not in roots:
                return node
            full = PurePosixPath(roots[base.id]).joinpath(*reversed(segments)).as_posix()
            if full not in exact_paths and full not in destinations:
                return node
            mapped, seen = full, set()
            while mapped in exact_paths and mapped not in seen:
                seen.add(mapped)
                mapped = exact_paths[mapped]
            # Retain the exact root binding name and predicate surrounding this
            # one mapped file. Partial prefixes, arbitrary calls and other roots
            # do not normalize; no change to an exists/is_file/negation check.
            return ast.Call(func=ast.Name(id="__preserved_literal_file__", ctx=ast.Load()),
                            args=[ast.Constant(base.id), ast.Constant(mapped)], keywords=[])


        def visit_Constant(self, node):
            if isinstance(node.value, str):
                original = node.value
                for old, new in literals:
                    # Match the exact mapped path/module, including a literal
                    # import statement used by source-contract tests. No numeric
                    # expectations, predicates, or other text is exempted.
                    original = re.sub(r"(?<![\w./])" + re.escape(old) + r"(?![\w])", lambda _: new, original)
                    if old.startswith("app.") and old.endswith(".__init__"):
                        # A mapped package initializer also has this exact import
                        # spelling. Do not extend the map to sibling modules or
                        # arbitrary directory-prefix descendants.
                        package = old.removesuffix(".__init__")
                        target = new.removesuffix(".__init__")
                        original = re.sub(
                            r"(?<![\w./])" + re.escape(package) + r"(?![\w./])",
                            lambda _: target,
                            original,
                        )
                node.value = original
            return node

    return ast.dump(Paths().visit(ast.parse(fragment)), include_attributes=False)


def check_assertions(snapshots: list[dict], targets: dict[str, str], files: dict[str, str], root: Path = ROOT,
                     symbols: dict[str, str] | None = None) -> list[str]:
    errors, cache, checked = [], {}, set()
    root_cache, frozen_root_cache = {}, {}
    literals = path_literals(files)
    symbols = symbols or {}
    for snapshot in snapshots:
        for node in snapshot["test_nodes"]:
            path, function = node_function(node)
            if function not in snapshot.get("test_assertions", {}).get(path, {}):
                errors.append(f"missing frozen assertion evidence: {node}")
        functions = {"::".join(node_function(node)): "::".join(node_function(targets[node])) for node in snapshot["test_nodes"]}
        # Helpers containing assertions remain protected even if the collected
        # test merely calls them. Their extraction needs an explicit symbol map.
        for old_path, old_functions in snapshot.get("test_assertions", {}).items():
          for old_function, expected in old_functions.items():
            node = f"{old_path}::{old_function}"
            full_symbol = f"backend/{old_path}::{old_function}"
            destination = symbols.get(full_symbol)
            if destination:
                new_path, new_function = node_function(destination.removeprefix("backend/"))
            elif node in functions:
                new_path, new_function = node_function(functions[node])
            else:
                new_path = files.get(f"backend/{old_path}", f"backend/{old_path}").removeprefix("backend/")
                new_function = old_function
            if not expected and node not in functions:
                continue
            identity = (old_path, old_function, new_path, new_function, digest(expected))
            if identity in checked:
                continue
            checked.add(identity)
            if new_path not in cache:
                source = (root / "backend" / new_path).resolve()
                if not source.is_relative_to((root / "backend/tests").resolve()) or not source.is_file():
                    cache[new_path] = {}
                else:
                    source_text = source.read_text(encoding="utf-8-sig")
                    cache[new_path] = assertion_contracts(source_text)
                    root_cache[new_path] = literal_path_roots(source_text, "backend/" + new_path)
            actual = cache[new_path].get(new_function)
            if actual is None:
                errors.append(f"missing test/helper function: {node} -> {new_path}::{new_function}")
                continue
            record = snapshot.get("tracked_files", {}).get("backend/" + old_path)
            blob = record.get("git_blob") if isinstance(record, dict) else record
            if blob and (old_path, blob) not in frozen_root_cache:
                text = git_bytes("cat-file", "blob", blob, root=root).decode("utf-8-sig")
                frozen_root_cache[(old_path, blob)] = literal_path_roots(text, "backend/" + old_path)
            old_roots = frozen_root_cache.get((old_path, blob), {}).get(old_function, {})
            new_roots = root_cache.get(new_path, {}).get(new_function, {})
            required = Counter(normalized_assertion(value, literals, roots=old_roots) for value in expected)
            # An unchanged synthetic legacy-path fixture and a migrated real
            # path assertion are equivalent under the same exact move map.
            # Normalize both sides; behavior predicates remain mandatory.
            found = Counter(normalized_assertion(value, literals, roots=new_roots) for value in actual)
            if required - found:
                errors.append(f"preserved assertion/exception expectation missing or changed: {node} -> {new_path}::{new_function}")
    return errors


def check_suppressions(snapshots: list[dict], files: dict[str, str], root: Path = ROOT) -> list[str]:
    errors, cache = [], {}
    literals = path_literals(files)
    for snapshot in snapshots:
        for old_path, expected in snapshot.get("test_suppressions", {}).items():
            path = files.get(f"backend/{old_path}", f"backend/{old_path}").removeprefix("backend/")
            if path not in cache:
                source = (root / "backend" / path).resolve()
                if not source.is_relative_to((root / "backend/tests").resolve()) or not source.is_file():
                    cache[path] = {}
                else:
                    cache[path] = suppression_contracts(source.read_text(encoding="utf-8-sig"))
            # Introducing a skip in a protected file (including conftest hooks)
            # requires an independently justified behavior change, not a move.
            required = {scope: [normalized_assertion(value, literals) for value in values] for scope, values in expected.items()}
            actual = {scope: [normalized_assertion(value, []) for value in values] for scope, values in cache[path].items()}
            if required != actual:
                errors.append(f"test skip/xfail suppression changed: {old_path} -> {path}")
    return errors


def check_sources(sources: list[str], files: dict[str, str], root: Path = ROOT) -> list[str]:
    errors = []
    for old, target in mapped_targets(sources, files).items():
        path = (root / target).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(f"source missing without a surviving mapped destination: {old} -> {target}")
        elif old.endswith(".py") and not old.endswith("/__init__.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            meaningful = [node for node in tree.body if not isinstance(node, ast.Pass) and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
            if not meaningful:
                errors.append(f"empty package marker or source cannot preserve implementation: {old} -> {target}")
    return errors


def defined_symbols(source: str) -> set[str]:
    symbols = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                symbols.add(alias.asname or alias.name.split(".")[0])
    return symbols


def check_split_evidence(moves: dict, snapshots: list[dict], root: Path = ROOT) -> list[str]:
    """A new split names actual symbols, consumers and surviving behavior tests.

    details[stage].split_files uses repository-relative old/new paths.
    details[stage].split_symbols is a list of {old: 'path.py::symbol',
    new: 'path.py::symbol', direct_consumers: ['path'], test_nodes: ['node']}.
    The already-reviewed pilot detail format is frozen at PR263, not extended.
    """
    historical = json.loads(git_bytes("show", f"{CHECKPOINT_COMMIT}:security/refactor_path_map.json", root=root)).get("details", {})
    errors = []
    for stage, detail in moves.get("details", {}).items():
        splits = detail.get("split_files", {})
        previous_splits = historical.get(stage, {}).get("split_files", {})
        for old_path, destinations in splits.items():
            if previous_splits.get(old_path) == destinations:
                continue
            if not old_path.startswith("backend/"):
                errors.append(f"{stage}: new backend split must name an exact repository-relative source: {old_path}")
                continue
            evidence = [entry for entry in detail.get("split_symbols", []) if entry.get("old", "").startswith(old_path + "::")]
            records = [snapshot["tracked_files"][old_path] for snapshot in snapshots if old_path in snapshot["tracked_files"]]
            if not records or not isinstance(destinations, list) or len(set(destinations)) < 2 or not evidence:
                errors.append(f"{stage}: split requires known source, multiple destinations and symbol/consumer/test evidence: {old_path}")
                continue
            blob = records[-1]
            source = git_bytes("cat-file", "blob", blob["git_blob"] if isinstance(blob, dict) else blob, root=root).decode("utf-8-sig")
            tree = ast.parse(source)
            owned = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            owned.update(target.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                         for target in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(target, ast.Name))
            covered, covered_destinations = set(), set()
            for entry in evidence:
                _, old_symbol = node_function(entry["old"])
                new_path, new_symbol = node_function(entry.get("new", ""))
                destination = (root / new_path).resolve()
                if old_symbol not in owned or new_path not in destinations or not destination.is_relative_to(root.resolve()) or not destination.is_file():
                    errors.append(f"{stage}: unknown or unsafe split symbol: {entry}")
                    continue
                if new_symbol not in defined_symbols(destination.read_text(encoding="utf-8-sig")):
                    errors.append(f"{stage}: split destination does not define the mapped symbol: {entry['new']}")
                consumers, tests = entry.get("direct_consumers", []), entry.get("test_nodes", [])
                if not consumers or not tests:
                    errors.append(f"{stage}: split symbol lacks direct consumers or behavior tests: {entry['old']}")
                for consumer in consumers:
                    candidate = (root / consumer).resolve()
                    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
                        errors.append(f"{stage}: split consumer missing or unsafe: {consumer}")
                for test in tests:
                    test_path, function = node_function(test)
                    candidate = (root / "backend" / test_path).resolve()
                    if not candidate.is_relative_to((root / "backend/tests").resolve()) or not candidate.is_file() or function not in assertion_contracts(candidate.read_text(encoding="utf-8-sig")):
                        errors.append(f"{stage}: split behavior test missing or unsafe: {test}")
                covered.add(old_symbol)
                covered_destinations.add(new_path)
            if owned - covered or set(destinations) - covered_destinations:
                errors.append(f"{stage}: split omits owned symbols or destinations: {old_path}; symbols={sorted(owned - covered)}; destinations={sorted(set(destinations) - covered_destinations)}")
    return errors


def addition_errors(additions: dict, checkpoint: dict, root: Path = ROOT) -> list[str]:
    """Validate provenance and append-only records against committed history.

    Records are appended in a metadata commit after their source commit exists.
    Their historical blob/assertion contents cannot be redefined by the worktree.
    """
    errors = []
    if additions.get("schema_version") != 1 or additions.get("checkpoint_commit") != checkpoint["commit"]:
        return ["invalid backend additions schema/checkpoint"]
    records, seen = additions.get("records", []), set()
    history_path = ADDITIONS.relative_to(ROOT).as_posix()
    history = git_bytes("log", "--format=%H", f"{checkpoint['commit']}..HEAD", "--", history_path, root=root).decode().splitlines()
    for commit in history:
        previous = json.loads(git_bytes("show", f"{commit}:{history_path}", root=root))
        old_records = previous.get("records", [])
        if records[:len(old_records)] != old_records:
            errors.append(f"backend additions history was changed or removed: {commit}")
            break
    for record in records:
        commit = record.get("commit", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"(?:K\d\d|G\d\d|AR-[A-Z0-9-]+)", record.get("feature_id", "")) or not record.get("reason"):
            errors.append("addition requires exact introduction commit, feature_id and reason")
            continue
        if commit in seen:
            errors.append(f"duplicate addition commit: {commit}")
            continue
        seen.add(commit)
        try:
            git_bytes("merge-base", "--is-ancestor", checkpoint["commit"], commit, root=root)
            git_bytes("merge-base", "--is-ancestor", commit, "HEAD", root=root)
            for path, blob in record.get("tracked_files", {}).items():
                source = git_bytes("show", f"{commit}:{path}", root=root)
                if git_blob(source) != blob:
                    errors.append(f"addition source provenance changed: {commit}:{path}")
                introduced = git_bytes("log", "--reverse", "--format=%H", "--diff-filter=A",
                                       f"{checkpoint['commit']}..{commit}", "--", path, root=root).decode().splitlines()
                if not introduced or introduced[0] != commit:
                    errors.append(f"addition source must name its first introduction commit: {path}")
            for path, functions in record.get("test_assertions", {}).items():
                source = git_bytes("show", f"{commit}:backend/{path}", root=root).decode("utf-8-sig")
                captured = assertion_contracts(source)
                for name, assertions in functions.items():
                    if captured.get(name) != assertions:
                        errors.append(f"addition assertion provenance changed: {commit}:{path}::{name}")
            protected = set(checkpoint["test_nodes"])
            for earlier in records:
                if earlier is record:
                    break
                protected.update(earlier.get("test_nodes", []))
            for node in record.get("test_nodes", []):
                path, name = node_function(node)
                if node in protected or name not in record.get("test_assertions", {}).get(path, {}):
                    errors.append(f"duplicate or unsupported addition node: {node}")
            for path, suppressions in record.get("test_suppressions", {}).items():
                source = git_bytes("show", f"{commit}:backend/{path}", root=root).decode("utf-8-sig")
                if suppression_contracts(source) != suppressions:
                    errors.append(f"addition suppression provenance changed: {commit}:{path}")
        except (ValueError, UnicodeError) as exc:
            errors.append(str(exc))
    return errors


def unrecorded_committed_sources(checkpoint: dict, snapshots: list[dict], file_targets: dict[str, str], root: Path = ROOT) -> list[str]:
    """A later commit may not omit the source evidence introduced before it.

    New uncommitted work is reviewable before capture. Once committed, append its
    immutable evidence in a following metadata commit before the PR can pass.
    """
    introduced = set(filter(None, git_bytes("log", "--format=", "--name-only", "--diff-filter=A", f"{checkpoint['commit']}..HEAD", root=root).decode().splitlines()))
    known = set(file_targets.values()).union(*(set(snapshot["tracked_files"]) for snapshot in snapshots))
    # The two metadata documents describe/protect themselves and are introduced
    # by this first support change, not by the frozen source checkpoint.
    metadata = {CHECKPOINT.relative_to(ROOT).as_posix(), ADDITIONS.relative_to(ROOT).as_posix()}
    return [f"committed source lacks append-only introduction evidence: {path}" for path in sorted(introduced - known - metadata)]


def unrecorded_committed_nodes(current: list[str], targets: dict[str, str], root: Path = ROOT) -> list[str]:
    tracked = {}
    for entry in git_bytes("ls-tree", "-r", "-z", "HEAD", "--", "backend/tests", root=root).decode().split("\0"):
        if entry:
            metadata, path = entry.split("\t", 1)
            tracked[path] = metadata.split()[2]
    errors, committed = [], {}
    for node in sorted(set(current) - set(targets.values())):
        path, _ = node_function(node)
        full = "backend/" + path
        if full not in committed:
            candidate = (root / full).resolve()
            committed[full] = candidate.is_relative_to(root.resolve()) and candidate.is_file() and git_blob(candidate.read_bytes().replace(b"\r\n", b"\n")) == tracked.get(full)
        if committed[full]:
            errors.append(f"committed test lacks append-only introduction evidence: {node}")
    return errors


def check_inventory(inventory: dict, baseline: dict, root: Path = ROOT) -> list[str]:
    errors = []
    if inventory.get("baseline_commit") != baseline["commit"]:
        errors.append("feature inventory baseline commit differs")
    items = inventory.get("items", [])
    ids = [item["id"] for item in items]
    required = {f"K{i:02}" for i in range(1, 24)} | {f"G{i:02}" for i in range(1, 14)}
    if len(ids) != len(set(ids)) or required - set(ids):
        errors.append("K01-K23/G01-G13 coverage is incomplete or duplicated")
    for item in items:
        for field in ("owner", "stage", "preserved_contracts", "current_paths", "target_paths", "verification", "disposition"):
            if not item.get(field):
                errors.append(f"{item['id']}: missing {field}")
        if item.get("status") not in {"MAPPED", "MOVED", "VERIFIED", "PROVEN_UNUSED"}:
            errors.append(f"{item['id']}: unresolved status")
        for path in item.get("current_paths", []) + item.get("test_paths", []):
            candidate = (root / path).resolve()
            if not candidate.is_relative_to(root.resolve()) or not candidate.exists():
                errors.append(f"{item['id']}: missing or unsafe path {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", action="store_true")
    parser.add_argument("--nodes", action="store_true")
    args = parser.parse_args()
    baseline_bytes = BASELINE.read_bytes()
    baseline = json.loads(baseline_bytes)
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    moves = json.loads(MOVES.read_text(encoding="utf-8"))
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    additions = json.loads(ADDITIONS.read_text(encoding="utf-8"))
    errors = check_inventory(inventory, baseline) + checkpoint_errors(checkpoint, baseline_bytes)
    try:
        errors.extend(addition_errors(additions, checkpoint))
        snapshots = [checkpoint, *additions["records"]]
        sources = sorted(set(baseline["tracked_files"]).union(*(set(snapshot["tracked_files"]) for snapshot in snapshots)))
        approved = sorted(set(baseline["test_nodes"]).union(*(set(snapshot["test_nodes"]) for snapshot in snapshots)))
        targets = mapped_targets(approved, moves["test_nodes"], nodes=True,
                                 node_snapshots=[baseline["test_nodes"], *(snapshot["test_nodes"] for snapshot in snapshots)])
        file_targets = mapped_targets(sources, moves["files"])
        errors.extend(check_sources(sources, moves["files"]))
        errors.extend(check_split_evidence(moves, [baseline, *snapshots]))
        errors.extend(unrecorded_committed_sources(checkpoint, snapshots, file_targets))
        symbol_snapshots = [[f"backend/{path}::{function}" for path, functions in snapshot.get("test_assertions", {}).items() for function in functions]
                            for snapshot in snapshots]
        symbols = mapped_targets(sorted(set().union(*(set(nodes) for nodes in symbol_snapshots))),
                                 moves.get("test_symbols", {}), nodes=True, node_snapshots=symbol_snapshots)
        errors.extend(check_assertions(snapshots, targets, file_targets,
                                      symbols={old: new for old, new in symbols.items() if old != new}))
        errors.extend(check_suppressions(snapshots, file_targets))
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
        targets = {}
    if args.contracts:
        contracts = current_contracts()
        for snapshot in (baseline, checkpoint):
            for name, values in snapshot["contracts"].items():
                if contracts.get(name) != values:
                    errors.append(f"API/ORM contract changed against {snapshot['commit']}: {name}; investigate, do not regenerate frozen evidence")
    if args.nodes:
        result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
                                cwd=ROOT / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            errors.append("pytest collection failed: " + result.stderr[-2000:])
        else:
            nodes = [line.strip() for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line]
            errors.extend("missing test: " + node for node in sorted(set(targets.values()) - set(nodes)))
            errors.extend(unrecorded_committed_nodes(nodes, targets))
            print(f"Frozen PR258 nodes={len(baseline['test_nodes'])}; PR263 nodes={len(checkpoint['test_nodes'])}; protected lineages={len(set(targets.values()))}; current={len(nodes)}")
    for message in errors:
        print(message, file=sys.stderr)
    if not errors:
        print(f"Refactor preservation passed: items={len(inventory['items'])}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
