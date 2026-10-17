"""Shared pinned scanner path for PR container gates and release candidates."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

TRIVY = "ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
SYFT = "anchore/syft:v1.51.0@sha256:678bfa565b60f747aac0f8e964fe5588a24445b8d0a480e91f6efd70020dfbb0"


def scan(images: list[str], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cache = "angmoo-release-scan-" + uuid.uuid4().hex
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    subprocess.run(["docker", "volume", "create", cache], check=True, env=env, stdout=subprocess.DEVNULL)
    docker = ["docker", "run", "--rm", "--volume", "/var/run/docker.sock:/var/run/docker.sock"]
    trivy = [*docker, "--volume", f"{cache}:/root/.cache/", TRIVY, "image"]
    try:
        for attempt in range(3):
            result = subprocess.run([*trivy, "--download-db-only", "--quiet"], env=env)
            if result.returncode == 0:
                break
            if attempt == 2:
                raise RuntimeError("scanner_database_unavailable")
            time.sleep(5)
        for number, image in enumerate(images):
            # Raw secret matches are never printed or uploaded. Only safe rule IDs.
            result = subprocess.run([*trivy, "--skip-db-update", "--ignore-unfixed", "--scanners", "vuln,secret", "--severity", "HIGH,CRITICAL", "--format", "json", image], check=True, stdout=subprocess.PIPE, env=env)
            payload = json.loads(result.stdout)
            findings = []
            for target in payload.get("Results") or []:
                findings.extend({"kind": "vulnerability", "id": v.get("VulnerabilityID"), "package": v.get("PkgName"), "installed": v.get("InstalledVersion"), "fixed": v.get("FixedVersion")} for v in target.get("Vulnerabilities") or [])
                findings.extend({"kind": "secret", "rule": s.get("RuleID")} for s in target.get("Secrets") or [])
            (output / f"image-{number}.security.json").write_text(json.dumps({"image": image, "scanner": TRIVY, "status": "FAIL" if findings else "PASS", "findings": findings}, indent=2) + "\n")
            if findings:
                raise RuntimeError("container_security_findings: " + json.dumps(findings))
            sbom = subprocess.run([*docker, SYFT, f"docker:{image}", "--output", "spdx-json"], check=True, stdout=subprocess.PIPE, env=env).stdout
            parsed = json.loads(sbom)
            if parsed.get("spdxVersion") != "SPDX-2.3" or not parsed.get("packages"):
                raise RuntimeError("invalid_sbom")
            (output / f"image-{number}.spdx.json").write_bytes(sbom)
    finally:
        subprocess.run(["docker", "volume", "rm", cache], check=True, env=env, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scan(args.image, args.output)
