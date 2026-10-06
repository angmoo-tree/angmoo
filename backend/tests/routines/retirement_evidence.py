"""Parse exact historical tests; never load or execute a retired SNS engine.

Exclusive old-engine test nodes survive as retirement proofs. Their former
assertions are archived by Git; supported behavior runs in the actual V2
integration suites named by this closed evidence, not in a test-only graph.
"""
import ast
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _evidence():
    evidence = json.loads((ROOT / "security/sns_retirement_evidence.json").read_text(encoding="utf-8"))
    assert evidence["schema_version"] == 1
    subprocess.run(["git", "merge-base", "--is-ancestor", evidence["source_commit"], "HEAD"],
                   cwd=ROOT, check=True, capture_output=True)
    before = subprocess.check_output(["git", "show", f"{evidence['source_commit']}:{evidence['source']}"], cwd=ROOT)
    symbols = {n.name for n in ast.parse(before.decode("utf-8-sig")).body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not (ROOT / evidence["source"]).exists()
    assert importlib.util.find_spec("app.runtime.resident.langgraph") is None
    # Check the entire product import closure, including imports local to a
    # function. An empty old module or a forwarding facade cannot satisfy it.
    for path in (ROOT / "backend/app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "app.runtime.resident.langgraph"
                if node.module == "app.runtime.resident":
                    assert all(alias.name != "langgraph" for alias in node.names)
            elif isinstance(node, ast.Import):
                assert all(alias.name != "app.runtime.resident.langgraph" for alias in node.names)
    for replacement in evidence["replacement_tests"]:
        source = ast.parse((ROOT / "backend" / replacement).read_text(encoding="utf-8-sig"))
        assert any(isinstance(n, ast.Assert) for n in ast.walk(source))
        assert not any(isinstance(n, ast.Attribute) and n.attr in {"skip", "xfail"} for n in ast.walk(source))
    return evidence, symbols


def assert_retired_test(path, name):
    evidence, symbols = _evidence()
    owned = evidence["cases"][path][name]
    assert owned and set(owned) <= symbols
    historical = subprocess.check_output(["git", "show", f"{evidence['source_commit']}:{path}"], cwd=ROOT)
    tests = {n.name: n for n in ast.parse(historical.decode("utf-8-sig")).body
             if isinstance(n, ast.FunctionDef)}
    assert name in tests and any(isinstance(n, ast.Assert) for n in ast.walk(tests[name]))
    from app.runtime.autonomous_activity.gateway import run_social_activity
    from app.runtime.resident import execution
    assert execution.run_social_activity is run_social_activity
    return {"entry": run_social_activity, "source_absent": not (ROOT / evidence["source"]).exists()}
