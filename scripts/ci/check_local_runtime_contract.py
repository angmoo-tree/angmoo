"""Validate the machine-readable L0 Docker runtime contract."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "security/local_runtime_contract.json"
DEFAULT_DOC = ROOT / "docs/public/local-runtime.md"
FORBIDDEN_CORE_PREFIXES = ("app.domains", "app.integrations", "app.runtime")
EXPECTED_DEFAULT_SERVICES = {"backend", "frontend"}
EXPECTED_STATES = {
    "blocked", "degraded", "healthy", "stale_state", "starting", "stopped", "stopping"
}
EXPECTED_ERROR_CODES = {
    "container_engine_unavailable", "data_path_unwritable", "database_unavailable",
    "graph_unavailable", "image_build_failed", "image_pull_failed", "migration_mismatch",
    "not_implemented_until_L5", "port_conflict", "projector_backlog",
    "provider_not_configured", "runtime_state_stale", "secret_mismatch",
    "secret_missing", "unsupported_tool_version",
}
EXPECTED_COMMANDS = {
    "user_start": ["docker", "compose", "up", "-d"],
    "contributor_start": [
        "docker", "compose", "-f", "compose.yml", "-f", "compose.dev.yml",
        "up", "--watch",
    ],
    "stop": ["docker", "compose", "down"],
}
EXPECTED_RELEASE_IMAGES = {
    "backend": {
        "default_tag": "v0.3.0",
        "repository": "ghcr.io/angmoo-tree/angmoo-backend",
    },
    "frontend": {
        "default_tag": "v0.3.0",
        "repository": "ghcr.io/angmoo-tree/angmoo-frontend",
    },
}
EXPECTED_SUPPLY_CHAIN = {
    "platform": "linux/amd64",
    "provenance": "github-artifact-attestation",
    "release_trigger": "v*.*.*",
    "sbom_format": "spdx-json",
    "secret_allowlist": "security/trivy-secret.yaml",
    "syft_image": (
        "anchore/syft:v1.51.0@sha256:"
        "678bfa565b60f747aac0f8e964fe5588a24445b8d0a480e91f6efd70020dfbb0"
    ),
    "trivy_image": (
        "ghcr.io/aquasecurity/trivy:0.74.0@sha256:"
        "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
    ),
}


def _core_modules(root: Path) -> set[str]:
    core = root / "backend/app/core"
    return {
        f"app.core.{path.stem}"
        for path in core.glob("*.py")
        if path.name != "__init__.py"
    }


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def validate_contract(payload: Any, *, root: Path = ROOT) -> list[str]:
    if not isinstance(payload, dict):
        return ["contract root must be an object"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("contract_id") != "angmoo-l0-docker-runtime-v1":
        errors.append("contract_id mismatch")
    if payload.get("canonical_commands") != EXPECTED_COMMANDS:
        errors.append("canonical_commands mismatch")
    if set(payload.get("default_services", [])) != EXPECTED_DEFAULT_SERVICES:
        errors.append("default_services must contain the two-service embedded stack")
    if set(payload.get("states", [])) != EXPECTED_STATES:
        errors.append("runtime states mismatch")
    if set(payload.get("error_codes", [])) != EXPECTED_ERROR_CODES:
        errors.append("runtime error codes mismatch")
    if payload.get("release_images") != EXPECTED_RELEASE_IMAGES:
        errors.append("release image contract mismatch")
    if payload.get("supply_chain") != EXPECTED_SUPPLY_CHAIN:
        errors.append("container supply-chain contract mismatch")

    publications = payload.get("host_publications")
    if not isinstance(publications, dict) or set(publications) != {"frontend"}:
        errors.append("only frontend may be published to the host")
    elif publications["frontend"] != {
        "address": "127.0.0.1",
        "default_port": 3000,
        "port_environment": "ANGMOO_PORT",
    }:
        errors.append("frontend host publication contract mismatch")

    if payload.get("embedded_storage") != {
        "canonical": "sqlite",
        "graph": "ladybug",
        "search": "fts5",
    }:
        errors.append("embedded storage contract mismatch")

    support = payload.get("support")
    if not isinstance(support, dict):
        errors.append("support contract must be an object")
    elif support.get("compose_minimum") != "2.22.0":
        errors.append("Compose 2.22.0 is required for the declared Watch contract")

    records = payload.get("core_modules")
    if not isinstance(records, list):
        errors.append("core_modules must be an array")
    else:
        modules = [record.get("module") for record in records if isinstance(record, dict)]
        if len(modules) != len(set(modules)):
            errors.append("core_modules contains duplicates")
        if set(modules) != _core_modules(root):
            errors.append("core module inventory is stale")
        for record in records:
            if not isinstance(record, dict):
                errors.append("core module entry must be an object")
                continue
            disposition = record.get("disposition")
            if disposition not in {"keep", "migrate", "remove"}:
                errors.append(f"invalid core disposition: {record.get('module')}")
            if not str(record.get("owner_stage", "")).strip():
                errors.append(f"core owner_stage is missing: {record.get('module')}")
            if disposition != "keep" and not str(record.get("removal_condition", "")).strip():
                errors.append(f"core removal_condition is missing: {record.get('module')}")

    for path in sorted((root / "backend/app/core").glob("*.py")):
        for imported in sorted(_imported_modules(path)):
            if imported.startswith(FORBIDDEN_CORE_PREFIXES):
                errors.append(
                    f"core imports an upper layer: {path.relative_to(root)} -> {imported}"
                )
    return errors


def check_repo(
    *, root: Path = ROOT, contract_path: Path = DEFAULT_CONTRACT, doc_path: Path = DEFAULT_DOC
) -> list[str]:
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
        errors = validate_contract(payload, root=root)
        document = doc_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError, SyntaxError) as exc:
        return [f"runtime contract cannot be read: {exc}"]
    for required in (
        "docker compose -f compose.yml -f compose.dev.yml up --watch",
        "angmoo_contributor_embedded_data",
        "CONTRIBUTOR_EMBEDDED",
        "SQLite",
        "LadybugDB",
    ):
        if required not in document:
            errors.append(f"local runtime document is missing: {required}")
    for required_path in (
        "Dockerfile.backend", "Dockerfile.frontend", ".dockerignore",
        "compose.yml", "compose.dev.yml", "compose.ci.yml",
        ".github/workflows/release-images.yml",
        "docs/public/container-release.md",
    ):
        if not (root / required_path).is_file():
            errors.append(f"local runtime asset is missing: {required_path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--document", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    errors = check_repo(
        root=args.repo_root.resolve(),
        contract_path=args.contract.resolve(),
        doc_path=args.document.resolve(),
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    payload = json.loads(args.contract.read_text(encoding="utf-8"))
    print(
        "L0 runtime contract passed: "
        f"services={len(payload['default_services'])} "
        f"core_modules={len(payload['core_modules'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
