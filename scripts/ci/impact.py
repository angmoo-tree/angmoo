"""Conservative CI impact selection, with an auditable fail-closed diff identity.

This helper uses the standard library so selection never depends on installing
the dependencies whose installation it is selecting. Unknown inputs select full.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "ci-impact.v1"
JOBS = ("backend", "frontend", "local-core-smoke", "local-autonomy-smoke", "local-full-graph",
        "embedded-data-migration", "tauri-windows", "windows-installer", "windows-native",
        "tauri-windows-host-dev")
FULL_PREFIXES = (".github/", "scripts/", "security/", "docker/", "deploy/", "desktop/")
FULL_FILES = {"Dockerfile", "Dockerfile.local", "compose.yml", "compose.local.yml", "Makefile",
              ".dockerignore", ".gitattributes", ".gitmodules"}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def classify(paths: list[str], *, force_full: bool = False, unknown_diff: bool = False) -> dict:
    jobs = {name: False for name in JOBS}
    reasons = []
    backend, selected = "none", []
    windows = "none"
    full = force_full or unknown_diff or not paths
    if full:
        reasons.append("explicit_full_or_unavailable_diff")
    for path in sorted(set(paths)):
        parts = PurePosixPath(path).parts
        if (not path or "\\" in path or path.startswith("/") or ".." in parts
                or path.startswith(FULL_PREFIXES) or path in FULL_FILES):
            full = True
            reasons.append(f"shared_build_policy_or_unknown:{path}")
        elif path.startswith("backend/tests/"):
            # Only isolated test modules qualify. Shared fixtures and test
            # configuration can change collection or every consumer.
            if path.endswith(".py") and PurePosixPath(path).name.startswith("test_"):
                selected.append(path.removeprefix("backend/"))
                jobs["backend"] = True
                if backend == "none":
                    backend = "scoped"
                reasons.append(f"test_module:{path}")
            else:
                full = True
                reasons.append(f"shared_test_input:{path}")
        elif path.startswith("backend/app/"):
            # Cross-domain, runtime, persistence and dynamic consumers make a
            # narrow path-only backend source map unsafe. Keep the whole corpus.
            backend = "full"
            for name in ("backend", "frontend", "local-core-smoke", "local-autonomy-smoke", "local-full-graph", "tauri-windows", "tauri-windows-host-dev"):
                jobs[name] = True
            windows = max((windows, "build"), key=("none", "build", "installer-smoke", "full").index)
            if any(part in path for part in ("/migrations/", "/persistence/", "/models/", "/installation/", "/security/", "/installer")):
                full = True
            reasons.append(f"backend_runtime:{path}")
        elif path.startswith("frontend/src/") or path.startswith("frontend/public/"):
            jobs.update({"frontend": True, "tauri-windows": True, "tauri-windows-host-dev": True})
            windows = max((windows, "build"), key=("none", "build", "installer-smoke", "full").index)
            reasons.append(f"frontend_product:{path}")
        elif path.startswith("browser-tests/") and path.endswith(".spec.ts"):
            jobs["frontend"] = True
            reasons.append(f"browser_suite:{path}")
        elif (path.startswith("docs/") and path.endswith(".md")) or path in {"README.md", "README.ko.md", "CONTRIBUTING.md", "CONTRIBUTING.ko.md", "AGENTS.md", "backend/ARCHITECTURE.md", "frontend/ARCHITECTURE.md", "frontend/DESIGN.md", "frontend/AGENTS.md"}:
            reasons.append(f"documentation:{path}")
        elif path in {"backend/uv.lock", "backend/pyproject.toml", "frontend/pnpm-lock.yaml", "frontend/package.json", "browser-tests/pnpm-lock.yaml", "browser-tests/package.json"}:
            # Runtime dependency and tool preparation changes get actual
            # installation plus representative upgrade; schema changes above
            # and any unknown build policy widen this to the complete matrix.
            jobs = {name: True for name in JOBS}
            backend, windows = "full", "installer-smoke"
            reasons.append(f"locked_dependency:{path}")
        else:
            full = True
            reasons.append(f"unmapped:{path}")
    if full:
        jobs, backend, windows, selected = {name: True for name in JOBS}, "full", "full", []
    if backend == "full":
        selected = []
    jobs["windows-installer"] = windows in {"installer-smoke", "full"}
    return {"backend": backend, "test_paths": sorted(set(selected)), "windows": windows,
            "jobs": jobs, "reasons": reasons, "paths": sorted(set(paths))}


def select_nodes(nodes: list[str], selection: dict, *, root: Path = ROOT) -> list[str]:
    if selection["backend"] == "full":
        return nodes[:]
    if selection["backend"] != "scoped":
        raise ValueError("backend_selection_not_required")
    files = sorted((root / "backend/tests").rglob("*.py"))
    selected = set(selection["test_paths"])
    # A test module can also supply fixtures to a different module. Include
    # static import consumers transitively, plus the directly affected suite.
    selected.update(str(p.relative_to(root / "backend")).replace("\\", "/") for p in files
        if any(str(p.relative_to(root / "backend")).replace("\\", "/").startswith(str(PurePosixPath(name).parent) + "/")
               for name in selected.copy() if len(PurePosixPath(name).parts) > 2))
    modules = {str(p.relative_to(root / "backend")).replace("\\", "/"): str(p.relative_to(root / "backend/tests").with_suffix("")).replace("\\", ".").replace("/", ".") for p in files}
    imports = {}
    for path in files:
        key = str(path.relative_to(root / "backend")).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        imports[key] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports[key].update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    package = modules[key].split(".")[:-1]
                    if node.level > len(package) + 1:
                        return nodes[:]
                    module = ".".join(package[:len(package) - node.level + 1] + ([module] if module else []))
                imports[key].add(module)
                imports[key].update(f"{module}.{alias.name}".strip(".") for alias in node.names)
            elif isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Name) and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
            ):
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    # A computed import can consume a changed test fixture.
                    # Expand the selected corpus instead of guessing its target.
                    return nodes[:]
                imports[key].add(node.args[0].value)
    while True:
        names = {modules.get(path, path.removeprefix("tests/").removesuffix(".py").replace("/", ".")) for path in selected}
        names.update("tests." + name for name in names.copy())
        added = {path for path, uses in imports.items() if any(use == name or use.startswith(name + ".") for use in uses for name in names)}
        if added <= selected:
            break
        selected.update(added)
    found = [node for node in nodes if node.partition("::")[0] in selected]
    # A removed test with no surviving consumer must not create a zero-test
    # required PASS. Run the current complete corpus to verify the removal.
    return found or nodes[:]


def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def changed_paths(base: str, head: str, *, pull_request: bool, root: Path = ROOT) -> list[str]:
    if any(re.fullmatch(r"[0-9a-f]{40}", ref or "") is None or ref == "0" * 40 for ref in (base, head)):
        raise ValueError("impact_diff_identity_invalid")
    if pull_request:
        base = git("merge-base", base, head, root=root)
    # --no-renames deliberately returns both the removed and added paths. A
    # rename across safety boundaries must retain the impact of either side.
    raw = subprocess.check_output(["git", "diff", "--name-only", "--no-renames", "-z", base, head, "--"], cwd=root)
    return sorted(set(filter(None, raw.decode("utf-8").split("\0"))))


def build_plan(*, event: dict, event_name: str, mode: str, requested: str, root: Path = ROOT) -> dict:
    checkout = git("rev-parse", "HEAD", root=root)
    pr = event.get("pull_request") or {}
    source = pr.get("head", {}).get("sha", checkout)
    base = pr.get("base", {}).get("sha", event.get("before", ""))
    paths, unavailable = [], False
    try:
        if event_name == "workflow_dispatch":
            base = git("merge-base", "origin/main", checkout, root=root)
        paths = changed_paths(base, source, pull_request=bool(pr), root=root)
        subprocess.run(["git", "merge-base", "--is-ancestor", source, checkout], cwd=root, check=True, capture_output=True)
    except (ValueError, subprocess.CalledProcessError, UnicodeError):
        unavailable = True
    manual = (event.get("inputs") or {}).get("profile", "full")
    full = requested == "full" or event_name == "schedule" or event_name == "workflow_dispatch" and manual != "auto"
    recommended = classify(paths, force_full=full, unknown_diff=unavailable)
    effective = classify(paths, force_full=True) if mode == "observe" else recommended
    policy = (root / "scripts/ci/impact.py").read_bytes()
    result = {"schema": SCHEMA, "mode": mode, "requested_profile": requested, "event": event_name, "source_sha": source,
              "base_sha": base, "checkout_sha": checkout, "checkout_tree": git("rev-parse", "HEAD^{tree}", root=root),
              "run_id": os.environ.get("GITHUB_RUN_ID", "0"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
              "rules_sha256": hashlib.sha256(policy).hexdigest(), "recommended": recommended, "effective": effective}
    result["selection_sha256"] = digest(effective)
    return result


def read_plan(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("mode") not in {"observe", "active"} or value.get("requested_profile") not in {"auto", "full"}:
        raise ValueError("impact_plan_profile_invalid")
    if value.get("schema") != SCHEMA or value.get("selection_sha256") != digest(value.get("effective")):
        raise ValueError("impact_plan_digest_invalid")
    if value["checkout_sha"] != git("rev-parse", "HEAD") or value["checkout_tree"] != git("rev-parse", "HEAD^{tree}"):
        raise ValueError("impact_plan_checkout_mismatch")
    if value["rules_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("impact_plan_rules_mismatch")
    for name, env in (("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT")):
        if value[name] != os.environ.get(env, "0" if name == "run_id" else "1"):
            raise ValueError("impact_plan_run_mismatch")
    if event_path := os.environ.get("GITHUB_EVENT_PATH"):
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        expected = build_plan(event=event, event_name=os.environ["GITHUB_EVENT_NAME"], mode=value["mode"], requested=value["requested_profile"])
        if expected != value:
            raise ValueError("impact_plan_does_not_match_actual_event")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".ci/impact.json"))
    parser.add_argument("--mode", choices=("observe", "active"), default="observe")
    parser.add_argument("--profile", choices=("auto", "full"), default="auto")
    args = parser.parse_args()
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
    result = build_plan(event=event, event_name=os.environ.get("GITHUB_EVENT_NAME", "local"), mode=args.mode, requested=args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = json.dumps(result, separators=(",", ":"))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"plan={compact}\n")
            stream.write(f"backend_profile={result['effective']['backend']}\n")
            stream.write(f"windows={result['effective']['windows']}\n")
            for key, value in result["effective"]["jobs"].items():
                stream.write(f"{key.replace('-', '_')}={str(value).lower()}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## CI impact selection\n\n```json\n" + json.dumps(result, indent=2) + "\n```\n")
    print(compact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
