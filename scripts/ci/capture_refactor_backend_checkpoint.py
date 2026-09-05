"""Capture immutable committed evidence; never collect from the working tree.

The checkpoint command creates the fixed PR263 snapshot once. After a source
commit introduces regressions, append its evidence in a following metadata commit:

  python scripts/ci/capture_refactor_backend_checkpoint.py --append COMMIT \
      --feature-id G01 --reason "Global config move regressions"

There is deliberately no overwrite/current-baseline option. Full Git history and
the backend's locked Python environment are required. Capture performs collection
and contract inspection, never lifespan execution or provider calls.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import check_refactor_preservation as preservation

ROOT = preservation.ROOT


def committed_snapshot(commit: str) -> dict:
    resolved = preservation.git_bytes("rev-parse", f"{commit}^{{commit}}").decode().strip()
    if resolved != commit:
        raise ValueError("capture requires an exact 40-character commit SHA")
    archive = preservation.git_bytes("archive", "--format=zip", commit)
    tree = preservation.git_bytes("rev-parse", f"{commit}^{{tree}}").decode().strip()
    tracked = {}
    for item in preservation.git_bytes("ls-tree", "-r", "-z", commit).decode().split("\0"):
        if item:
            metadata, path = item.split("\t", 1)
            _, kind, blob = metadata.split()
            if kind == "blob":
                tracked[path] = blob
    with tempfile.TemporaryDirectory(prefix="angmoo-committed-checkpoint-") as directory:
        snapshot_root = Path(directory)
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            bundle.extractall(snapshot_root)
        env = os.environ.copy()
        env.update({"APP_ENV": "test", "DATABASE_URL": "sqlite+pysqlite:///:memory:",
                    "GRAPH_PROVIDER": "ladybug", "LOCAL_RUNTIME_COMPONENT_MODE": "in_process",
                    "RESIDENT_TICK_SCHEDULER_ENABLED": "false", "POST_IMAGE_JOB_WORKER_ENABLED": "false",
                    "PYTHONPATH": str(snapshot_root / "backend")})
        result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
                                cwd=snapshot_root / "backend", env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise ValueError("committed collection failed: " + result.stdout[-3000:] + result.stderr[-1000:])
        nodes = sorted(line.strip() for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line)
        assertions = {}
        for path in sorted({preservation.node_function(node)[0] for node in nodes}):
            assertions[path] = preservation.assertion_contracts((snapshot_root / "backend" / path).read_text(encoding="utf-8-sig"))
        suppressions = {path.removeprefix("backend/"): preservation.suppression_contracts((snapshot_root / path).read_text(encoding="utf-8-sig"))
                        for path in tracked if path.startswith("backend/tests/") and path.endswith(".py")}
        code = "import importlib.util,json; from pathlib import Path; p=Path('scripts/ci/check_refactor_preservation.py'); s=importlib.util.spec_from_file_location('capture',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('CONTRACT_JSON='+json.dumps(m.current_contracts(),sort_keys=True))"
        result = subprocess.run([sys.executable, "-c", code], cwd=snapshot_root, env=env,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise ValueError("committed contract capture failed: " + result.stderr[-2000:])
        contracts = json.loads(next(line.removeprefix("CONTRACT_JSON=") for line in result.stdout.splitlines() if line.startswith("CONTRACT_JSON=")))
        moves = json.loads((snapshot_root / "security/refactor_path_map.json").read_text(encoding="utf-8"))
    return {"commit": commit, "tree": tree, "tracked_files": tracked,
            "test_nodes": nodes, "test_assertions": assertions, "test_suppressions": suppressions,
            "contracts": contracts, "path_map": moves}


def unprotected_files(tracked: dict[str, str], approved: list[str], moves: dict[str, str]) -> dict[str, str]:
    # A frozen old path may still exist as a temporary re-export bridge while
    # its actual implementation lives at the mapped destination. Neither is a
    # newly introduced source merely because the map names the other location.
    known = set(approved) | set(preservation.mapped_targets(approved, moves).values())
    return {path: blob for path, blob in tracked.items() if path not in known}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture-checkpoint", action="store_true")
    group.add_argument("--append", metavar="COMMIT")
    parser.add_argument("--feature-id")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.capture_checkpoint:
        if preservation.CHECKPOINT.exists():
            raise ValueError("checkpoint already exists; restore it from Git, never overwrite it")
        captured = committed_snapshot(preservation.CHECKPOINT_COMMIT)
        captured.pop("path_map")
        checkpoint = {"schema_version": 1,
                      "purpose": "Frozen PR263 backend transition checkpoint, additive to immutable PR258 evidence. Never regenerate after refactoring.",
                      "original_baseline_commit": "6e56f0837cc11ff42ccbb520050bbd32c5e9bc14",
                      "original_baseline_git_blob": preservation.BASELINE_BLOB,
                      **captured}
        preservation.CHECKPOINT.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"Captured committed PR263 files={len(checkpoint['tracked_files'])} nodes={len(checkpoint['test_nodes'])} digest={preservation.digest(checkpoint)}")
        return 0
    if not args.feature_id or not args.reason:
        raise ValueError("append requires --feature-id and --reason")
    checkpoint = json.loads(preservation.CHECKPOINT.read_text(encoding="utf-8"))
    additions = json.loads(preservation.ADDITIONS.read_text(encoding="utf-8"))
    existing_errors = preservation.checkpoint_errors(checkpoint, preservation.BASELINE.read_bytes()) + preservation.addition_errors(additions, checkpoint)
    if existing_errors:
        raise ValueError("; ".join(existing_errors))
    captured = committed_snapshot(args.append)
    baseline = json.loads(preservation.BASELINE.read_text(encoding="utf-8"))
    previous = [baseline, checkpoint, *additions["records"]]
    approved_nodes = sorted(set().union(*(set(snapshot["test_nodes"]) for snapshot in previous)))
    approved_files = sorted(set().union(*(set(snapshot["tracked_files"]) for snapshot in previous)))
    known_nodes = set(preservation.mapped_targets(approved_nodes, captured["path_map"]["test_nodes"], nodes=True,
                      node_snapshots=[snapshot["test_nodes"] for snapshot in previous]).values())
    new_nodes = sorted(set(captured["test_nodes"]) - known_nodes)
    new_files = unprotected_files(captured["tracked_files"], approved_files, captured["path_map"]["files"])
    assertions = {}
    for node in new_nodes:
        path, function = preservation.node_function(node)
        assertions[path] = captured["test_assertions"][path]
    suppressions = {path: captured["test_suppressions"][path] for path in assertions}
    if not new_nodes and not new_files:
        raise ValueError("commit introduces no unprotected source or test nodes")
    additions["records"].append({"commit": args.append, "feature_id": args.feature_id, "reason": args.reason,
                                 "tracked_files": new_files, "test_nodes": new_nodes, "test_assertions": assertions,
                                 "test_suppressions": suppressions})
    errors = preservation.addition_errors(additions, checkpoint)
    if errors:
        raise ValueError("; ".join(errors))
    preservation.ADDITIONS.write_text(json.dumps(additions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Appended committed evidence: sources={len(new_files)} nodes={len(new_nodes)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
