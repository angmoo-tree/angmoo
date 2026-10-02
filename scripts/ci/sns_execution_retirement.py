"""Validate exact, committed retirement of the two unsupported SNS engines.

This distinguishes retained symbol ownership from deliberately removed runtime
behavior. It does not regenerate a baseline or exempt arbitrary source files.
"""
import ast
from pathlib import Path

ALLOWED = frozenset({
    "backend/app/runtime/resident/langgraph.py",
    "backend/app/runtime/social/feed_cycle.py",
    "backend/app/runtime/social/feed_reaction_provider.py",
})


def definitions(source):
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result[node.name] = ast.dump(node, include_attributes=False)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    result[target.id] = ast.dump(node, include_attributes=False)
    return result


def validate(records, *, root, reader):
    removed, modules = set(), set()
    for record in records:
        for item in record.get("retired_sns_modules", []):
            source = item["source"]
            if source not in ALLOWED or source in modules or (root / source).exists():
                raise ValueError("SNS retirement requires one allowed, physically absent module")
            commit = record["implementation_commit"]
            before = reader("show", f"{commit}^:{source}", root=root)
            blob = reader("rev-parse", f"{commit}^:{source}", root=root).decode().strip()
            if blob != item["before_blob"]:
                raise ValueError("SNS retirement committed preimage differs")
            # A committed deletion, not an ignored local disappearance.
            tree = reader("ls-tree", commit, "--", source, root=root).strip()
            if tree:
                raise ValueError("SNS retirement source remains in the implementation commit")
            owned = definitions(before.decode("utf-8-sig"))
            retired = set(item["retired_symbols"])
            moved = item["moved_symbols"]
            if not owned or retired.intersection(moved) or retired | set(moved) != set(owned):
                raise ValueError("SNS retirement must account for every owned symbol exactly once")
            for symbol, destination in moved.items():
                path, name = destination["source"], destination["symbol"]
                if path not in record["source_blobs"] or path in ALLOWED:
                    raise ValueError("SNS retained ownership needs committed actual source")
                frozen = definitions(reader("show", f"{commit}:{path}", root=root).decode("utf-8-sig"))
                actual = definitions((root / path).read_text(encoding="utf-8-sig"))
                if (destination["before_ast"] != owned[symbol]
                        or frozen.get(name) != destination["after_ast"]
                        or actual.get(name) != destination["after_ast"]):
                    raise ValueError("SNS retained symbol differs from exact reviewed ownership")
            for test in item["successor_tests"]:
                path, name = test.split("::", 1)
                candidate = (root / "backend" / path).resolve()
                if not candidate.is_relative_to((root / "backend/tests").resolve()):
                    raise ValueError("SNS successor test path is unsafe")
                functions = {node.name: node for node in ast.parse(candidate.read_text(encoding="utf-8-sig")).body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                function = functions.get(name)
                if function is None or not any(isinstance(node, ast.Assert) for node in ast.walk(function)):
                    raise ValueError("SNS successor behavior test is missing")
                if any(isinstance(node, ast.Attribute) and node.attr in {"skip", "xfail"} for node in ast.walk(function)):
                    raise ValueError("SNS successor test cannot be suppressed")
            if not item["successor_tests"]:
                raise ValueError("SNS retirement lacks current behavior tests")
            removed.update((source, symbol) for symbol in retired)
            modules.add(source)
    if not modules:
        return removed, modules
    retired_modules = {path.removeprefix("backend/").removesuffix(".py").replace("/", ".") for path in modules}
    for path in (root / "backend/app").rglob("*.py"):
        module = path.relative_to(root / "backend").with_suffix("").as_posix().replace("/", ".")
        package = module.removesuffix(".__init__") if path.name == "__init__.py" else module.rpartition(".")[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (isinstance(node, ast.Call) and node.args
                    and (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
                         or isinstance(node.func, ast.Name) and node.func.id == "__import__")
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value in retired_modules):
                raise ValueError("retired SNS module has a dynamic product import: " + module)
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = package.split(".")[:len(package.split(".")) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                imports = [base, *(base + "." + alias.name for alias in node.names)]
            else:
                continue
            if any(name in retired_modules or any(name.startswith(old + ".") for old in retired_modules) for name in imports):
                raise ValueError("retired SNS module has an actual product import: " + module)
    return removed, modules
