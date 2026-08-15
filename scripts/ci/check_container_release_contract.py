"""Validate L0 Quickstart, container Gate, and tag-only GHCR publication."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = Path(".github/workflows/release-images.yml")
ACTION_REFS = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8",
    "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a",
    "docker/login-action@dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c",
}
TRIVY_IMAGE = (
    "ghcr.io/aquasecurity/trivy:0.74.0@"
    "sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
SYFT_IMAGE = (
    "anchore/syft:v1.51.0@"
    "sha256:678bfa565b60f747aac0f8e964fe5588a24445b8d0a480e91f6efd70020dfbb0"
)
USES = re.compile(r"(?m)^\s*(?:-\s+)?uses:\s+([^\s#]+)")


def _events(document: dict[object, object]) -> Any:
    if "on" in document:
        return document["on"]
    return document.get(True)


def validate_contract(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    workflow_path = root / WORKFLOW
    required_files = (
        workflow_path,
        root / "compose.ci.yml",
        root / "scripts/ci/check_container_images.py",
        root / "scripts/ci/check_release_tag.py",
        root / "scripts/ci/run_container_gate.sh",
        root / "scripts/ci/run_l0_container_smoke.py",
        root / "security/trivy-secret.yaml",
        root / "docs/public/container-release.md",
    )
    for path in required_files:
        if not path.is_file():
            errors.append(f"container release asset is missing: {path.relative_to(root)}")
    if errors:
        return errors

    text = workflow_path.read_text(encoding="utf-8")
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f"release workflow YAML is invalid: {exc}"]
    if not isinstance(document, dict):
        return ["release workflow root must be a mapping"]
    events = _events(document)
    if not isinstance(events, dict) or set(events) != {"push"}:
        errors.append("release workflow must be triggered only by push tags")
    else:
        push = events.get("push")
        if not isinstance(push, dict) or push.get("tags") != ["v*.*.*"]:
            errors.append("release workflow must accept only semantic v*.*.* tags")
        elif "branches" in push:
            errors.append("release workflow must not publish from a branch push")
    if document.get("permissions") != {"contents": "read"}:
        errors.append("release workflow top-level permissions must be contents: read")

    jobs = document.get("jobs")
    publish = jobs.get("publish-ghcr") if isinstance(jobs, dict) else None
    if not isinstance(publish, dict):
        errors.append("publish-ghcr job is missing")
    else:
        expected_permissions = {
            "attestations": "write",
            "contents": "read",
            "id-token": "write",
            "packages": "write",
        }
        if publish.get("permissions") != expected_permissions:
            errors.append("publish-ghcr permissions do not match the minimum release set")
        if publish.get("if") != "github.repository == 'angmoo-tree/angmoo'":
            errors.append("fork tag publication must be disabled")

    actual_actions = set(USES.findall(text))
    if actual_actions != ACTION_REFS:
        errors.append(
            f"release action inventory mismatch: actual={sorted(actual_actions)}"
        )
    required_markers = (
        "python scripts/ci/check_release_tag.py",
        "bash scripts/ci/run_container_gate.sh",
        "push: true",
        "provenance: mode=max",
        "sbom: true",
        "push-to-registry: true",
        "ghcr.io/angmoo-tree/angmoo-backend",
        "ghcr.io/angmoo-tree/angmoo-frontend",
        "sha-${{ github.sha }}",
        "password: ${{ github.token }}",
    )
    for marker in required_markers:
        if marker not in text:
            errors.append(f"release workflow marker is missing: {marker}")
    if "pull_request" in text or "secrets." in text:
        errors.append("release workflow must not run on PRs or require repository secrets")

    gate = (root / "scripts/ci/run_container_gate.sh").read_text(encoding="utf-8")
    for image in (TRIVY_IMAGE, SYFT_IMAGE):
        if image not in gate:
            errors.append(f"supply-chain tool image is not immutable: {image}")
    for marker in (
        "--ignore-unfixed",
        "--secret-config /etc/trivy-secret.yaml",
        "--severity HIGH,CRITICAL",
        "--output spdx-json",
    ):
        if marker not in gate:
            errors.append(f"container Gate marker is missing: {marker}")

    secret_config = (root / "security/trivy-secret.yaml").read_text(encoding="utf-8")
    for marker in (
        "oci-golden-gate-sas-documentation-example",
        "site-packages/oci/golden_gate/models/",
        "create|update",
    ):
        if marker not in secret_config:
            errors.append(f"Trivy allow rule marker is missing: {marker}")

    compose = (root / "compose.yml").read_text(encoding="utf-8")
    for marker in (
        "ghcr.io/angmoo-tree/angmoo-backend:${ANGMOO_VERSION:-v0.1.0}",
        "ghcr.io/angmoo-tree/angmoo-frontend:${ANGMOO_VERSION:-v0.1.0}",
    ):
        if marker not in compose:
            errors.append(f"release Compose image marker is missing: {marker}")
    compose_ci = (root / "compose.ci.yml").read_text(encoding="utf-8")
    for marker in ("angmoo-backend-ci:", "angmoo-frontend-ci:", "pull_policy: never"):
        if marker not in compose_ci:
            errors.append(f"CI Compose override marker is missing: {marker}")

    docs = {
        "README.md": "docker compose up -d",
        "README.ko.md": "docker compose up -d",
        "CONTRIBUTING.md": "docker compose -f compose.yml -f compose.dev.yml up --watch",
        "CONTRIBUTING.ko.md": "docker compose -f compose.yml -f compose.dev.yml up --watch",
    }
    for relative, command in docs.items():
        if command not in (root / relative).read_text(encoding="utf-8"):
            errors.append(f"canonical Docker command is missing: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate_contract(args.repo_root.resolve())
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("L0 container release contract passed: tag-only GHCR + required image Gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
