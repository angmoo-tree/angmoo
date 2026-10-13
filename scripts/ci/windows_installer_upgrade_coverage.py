"""Exact native upgrade coverage; no product/database/credential contents."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PARTITIONS = ("first", "second")
SCHEMA = "windows-installer-upgrade-coverage.v1"


def readable_predecessors(root: Path = ROOT) -> tuple[int, ...]:
    source = (root / "backend/app/runtime/persistence/sqlite_schema.py").read_text(encoding="utf-8-sig")
    versions = [ast.literal_eval(node.value) for node in ast.parse(source).body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
            and target.id == "SQLITE_SCHEMA_VERSION" for target in node.targets)]
    if len(versions) != 1 or type(versions[0]) is not int or versions[0] < 2:
        raise ValueError("installer_current_schema_invalid")
    current = versions[0]
    manifests = root / "backend/app/runtime/migrations/sqlite_versions/manifests"
    for version in range(1, current + 1):
        if json.loads((manifests / f"v{version}.json").read_text(encoding="utf-8"))["schema_version"] != version:
            raise ValueError("installer_predecessor_manifest_invalid")
    return tuple(range(1, current))


def partition_versions(versions: tuple[int, ...], partition: str) -> tuple[int, ...]:
    if not versions or versions != tuple(range(1, len(versions) + 1)):
        raise ValueError("installer_predecessor_set_invalid")
    if partition == "all":
        return versions
    if partition == "representative":
        return tuple(dict.fromkeys((versions[0], versions[-1])))
    if partition not in PARTITIONS:
        raise ValueError("installer_upgrade_partition_invalid")
    boundary = (len(versions) + 1) // 2
    return versions[:boundary] if partition == "first" else versions[boundary:]


def verify_reports(reports: list[dict], *, versions: tuple[int, ...], source_sha: str,
                   run_id: str, run_attempt: str, profile: str = "full") -> dict:
    if (re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
            or re.fullmatch(r"[0-9]+", run_id) is None
            or re.fullmatch(r"[1-9][0-9]*", run_attempt) is None):
        raise ValueError("installer_upgrade_identity_invalid")
    if profile not in {"full", "installer-smoke"}:
        raise ValueError("installer_coverage_profile_invalid")
    partitions = PARTITIONS if profile == "full" else ("representative",)
    expected_versions = versions if profile == "full" else partition_versions(versions, "representative")
    if len(reports) != len(partitions) or {r.get("partition") for r in reports} != set(partitions):
        raise ValueError("installer_upgrade_partitions_missing")
    covered = []
    fields = {"schema", "status", "source_sha", "run_id", "run_attempt", "partition", "versions", "idempotent"}
    for report in reports:
        if (set(report) != fields or report.get("schema") != SCHEMA
                or report.get("status") != "completed" or report.get("idempotent") is not True):
            raise ValueError("installer_upgrade_report_incomplete")
        if (report["source_sha"], str(report["run_id"]), str(report["run_attempt"])) != (source_sha, run_id, run_attempt):
            raise ValueError("installer_upgrade_report_identity_mismatch")
        selected = list(partition_versions(versions, report["partition"]))
        if report["versions"] != selected or any(type(v) is not int for v in report["versions"]):
            raise ValueError("installer_upgrade_partition_coverage_mismatch")
        covered.extend(selected)
    if len(covered) != len(set(covered)) or set(covered) != set(expected_versions):
        raise ValueError("installer_upgrade_union_incomplete")
    return {"schema": SCHEMA, "source_sha": source_sha, "run_id": run_id,
        "run_attempt": run_attempt, "profile": profile, "covered": len(covered), "versions": list(expected_versions), "partitions": len(partitions)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select-partition", choices=(*PARTITIONS, "all", "representative"))
    parser.add_argument("--profile", choices=("full", "installer-smoke"), default="full")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--run-id")
    parser.add_argument("--run-attempt")
    args = parser.parse_args()
    versions = readable_predecessors()
    if args.select_partition:
        print(json.dumps(partition_versions(versions, args.select_partition)))
        return 0
    if not args.directory or not args.source_sha or not args.run_id or not args.run_attempt:
        parser.error("supply selection or directory and exact run identity")
    files = sorted(args.directory.rglob("angmoo-supported-upgrade-*.json"))
    if len(files) != (2 if args.profile == "full" else 1) or any(path.stat().st_size > 4096 or path.is_symlink() for path in files):
        raise ValueError("installer_upgrade_report_files_invalid")
    reports = [json.loads(path.read_text(encoding="utf-8-sig")) for path in files]
    print(json.dumps(verify_reports(reports, versions=versions, source_sha=args.source_sha,
                                   run_id=args.run_id, run_attempt=args.run_attempt, profile=args.profile)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
