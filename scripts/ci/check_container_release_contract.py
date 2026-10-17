"""Validate product identity, both platforms and build-once publication."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.release.workflow_policy import validate, uploads, WORKFLOWS
from scripts.ci.check_release_tag import validate_release_tag


def validate_contract(root: Path = ROOT) -> list[str]:
    errors = validate_release_tag("release-v0.1.0", root)
    for name in sorted(WORKFLOWS):
        path = root / ".github/workflows" / name
        if not path.is_file():
            errors.append(f"release workflow missing: {name}")
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors.extend(validate(doc, name))
        errors.extend(uploads(doc, name))
    compose = yaml.safe_load((root / "compose.yml").read_text(encoding="utf-8"))
    ci = yaml.safe_load((root / "compose.ci.yml").read_text(encoding="utf-8"))
    for service in ("backend", "frontend"):
        expected = "ghcr.io/angmoo-tree/angmoo-" + service + ":${ANGMOO_IMAGE_TAG:-release-v0.1.0}"
        if compose["services"][service].get("image") != expected:
            errors.append(f"image selection must be separate from product version: {service}")
        if ci["services"][service].get("platform") != "${ANGMOO_CI_PLATFORM:-linux/amd64}" or ci["services"][service].get("pull_policy") != "never":
            errors.append(f"CI must use the imported candidate for its explicit platform: {service}")
    scanner = (root / "scripts/release/scan.py").read_text()
    for marker in ("ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969",
                   "anchore/syft:v1.51.0@sha256:678bfa565b60f747aac0f8e964fe5588a24445b8d0a480e91f6efd70020dfbb0",
                   "--ignore-unfixed", "vuln,secret", "HIGH,CRITICAL", "spdx-json"):
        if marker not in scanner:
            errors.append(f"required supply-chain check missing: {marker}")
    gate = (root / "scripts/ci/run_container_gate.sh").read_text()
    if "scripts.release.scan" not in gate or "--development" not in gate:
        errors.append("PR gate must reuse supply-chain checks and retain development smoke")
    for relative in ("README.md", "README.ko.md", "CONTRIBUTING.md", "CONTRIBUTING.ko.md"):
        if "docker compose -f compose.yml -f compose.dev.yml up --watch" not in (root / relative).read_text(encoding="utf-8"):
            errors.append(f"canonical contributor command missing: {relative}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate_contract(args.repo_root.resolve())
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Container release contract passed: explicit platforms, verified promotion, guarded publication")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
