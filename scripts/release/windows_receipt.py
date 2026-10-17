"""Bind successful installer jobs and full upgrade coverage to one exact EXE."""

import argparse
import json
import os
from pathlib import Path

from launcher.termux.payload import digest_file, require
from scripts.ci.windows_installer_upgrade_coverage import readable_predecessors, verify_reports
from scripts.release.candidate import write_json

KINDS = {"clean-install", "failure-recovery", "upgrade-first", "upgrade-second"}


def tested_installer(root: Path) -> dict:
    files = list(root.rglob("Angmoo_*_x64-setup.exe"))
    require(len(files) == 1 and not files[0].is_symlink(), "installer_not_unique")
    checksums = list(root.rglob("SHA256SUMS"))
    require(len(checksums) == 1, "installer_checksums_missing")
    sha = digest_file(files[0])
    require(checksums[0].read_text().strip() == f"{sha[7:]}  {files[0].name}", "installer_checksums_mismatch")
    return {"name": files[0].name, "sha256": sha, "size": files[0].stat().st_size}


def aggregate(receipts: list[dict], reports: list[dict], *, source: str, run: str, attempt: str) -> dict:
    require(len(receipts) == 4 and {r.get("kind") for r in receipts} == KINDS, "installer_jobs_missing")
    first = receipts[0]
    for receipt in receipts:
        require(receipt.get("schema") == "angmoo-installer-test.v1" and receipt.get("status") == "PASS", "installer_job_failed")
        require((receipt.get("source_sha"), str(receipt.get("run_id")), str(receipt.get("attempt"))) == (source, run, attempt), "installer_receipt_identity_mismatch")
        require(receipt.get("exe") == first["exe"] and receipt.get("artifact_id") == first["artifact_id"], "installer_tested_bytes_differ")
    coverage = verify_reports(reports, versions=readable_predecessors(), source_sha=source, run_id=run, run_attempt=attempt, profile="full")
    return {"schema": "angmoo-windows-release-validation.v1", "source_sha": source, "run_id": run, "attempt": attempt, "profile": "full", "status": "PASS", "exe": first["exe"], "artifact_id": first["artifact_id"], "coverage": coverage, "jobs": receipts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("job")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--kind", choices=sorted(KINDS), required=True)
    p.add_argument("--artifact-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("aggregate")
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--coverage", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, run, attempt = (os.environ[k] for k in ("SOURCE_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if args.command == "job":
        require(args.artifact_id.isdecimal(), "installer_artifact_id_invalid")
        result = {"schema": "angmoo-installer-test.v1", "source_sha": source, "run_id": run, "attempt": attempt, "kind": args.kind, "status": "PASS", "artifact_id": args.artifact_id, "exe": tested_installer(args.root)}
    else:
        result = aggregate([json.loads(p.read_text()) for p in args.receipts.glob("*.json")], [json.loads(p.read_text(encoding="utf-8-sig")) for p in args.coverage.glob("angmoo-supported-upgrade-*.json")], source=source, run=run, attempt=attempt)
    write_json(args.output, result)


if __name__ == "__main__":
    main()
