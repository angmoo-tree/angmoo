"""Validate the official two-service embedded Docker contributor runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SERVICES = {"backend", "frontend"}
EXPECTED_VOLUMES = {"angmoo_contributor_embedded_data"}
FORBIDDEN_ENVIRONMENT = {
    "APP_SECRET",
    "DATABASE_URL",
    "NEO4J_AUTH",
    "NEO4J_PASSWORD",
    "POSTGRES_PASSWORD",
}


def _environment_keys(service: dict[str, Any]) -> set[str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return set(environment)
    if isinstance(environment, list):
        return {str(item).split("=", 1)[0] for item in environment}
    return set()


def validate_resolved_compose(
    release: Any, development: Any, *, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    if not isinstance(release, dict) or not isinstance(release.get("services"), dict):
        return ["release Compose config is not an object with services"]
    services: dict[str, Any] = release["services"]
    if set(services) != EXPECTED_SERVICES:
        errors.append("official Compose must contain only backend and frontend")

    for name, service in services.items():
        if not isinstance(service, dict):
            errors.append(f"service must be an object: {name}")
            continue
        ports = service.get("ports", [])
        if name == "frontend":
            if len(ports) != 1:
                errors.append("frontend must have exactly one host publication")
            else:
                port = ports[0]
                if (
                    not isinstance(port, dict)
                    or port.get("host_ip") != "127.0.0.1"
                    or port.get("target") != 3000
                ):
                    errors.append(
                        "frontend must publish only 127.0.0.1 to container 3000"
                    )
        elif ports:
            errors.append(f"only frontend may publish a host port: {name}")
        if not service.get("healthcheck"):
            errors.append(f"service healthcheck is missing: {name}")
        exposed = FORBIDDEN_ENVIRONMENT & _environment_keys(service)
        if exposed:
            errors.append(f"plaintext or legacy runtime environment is forbidden: {name}")

    backend = services.get("backend", {})
    if isinstance(backend, dict):
        if backend.get("command") != ["contributor-api"]:
            errors.append("backend must use the typed contributor entrypoint")
        environment = backend.get("environment", {})
        if not isinstance(environment, dict) or environment.get(
            "ANGMOO_CONTRIBUTOR_DATA_ROOT"
        ) != "/var/lib/angmoo":
            errors.append("backend embedded data root mismatch")
        mounts = backend.get("volumes", [])
        if not any(
            isinstance(mount, dict)
            and mount.get("source") == "angmoo_contributor_embedded_data"
            and mount.get("target") == "/var/lib/angmoo"
            for mount in mounts
        ):
            errors.append("backend embedded data volume is missing")

    volumes = release.get("volumes", {})
    if not isinstance(volumes, dict) or set(volumes) != EXPECTED_VOLUMES:
        errors.append("official Compose named volume inventory mismatch")

    if not isinstance(development, dict) or not isinstance(
        development.get("services"), dict
    ):
        errors.append("development Compose config is not an object with services")
    else:
        dev_services: dict[str, Any] = development["services"]
        if set(dev_services) != EXPECTED_SERVICES:
            errors.append("development Compose must remain a two-service runtime")
        for name in EXPECTED_SERVICES:
            service = dev_services.get(name)
            if not isinstance(service, dict) or not service.get("build"):
                errors.append(f"development service must build locally: {name}")
                continue
            develop = service.get("develop", {})
            if not isinstance(develop, dict) or not develop.get("watch"):
                errors.append(f"Compose Watch is missing: {name}")
        dev_backend = dev_services.get("backend", {})
        if isinstance(dev_backend, dict) and dev_backend.get("command") != [
            "contributor-api-dev"
        ]:
            errors.append("development backend must enable embedded reload")
        dev_frontend = dev_services.get("frontend", {})
        command = dev_frontend.get("command", []) if isinstance(dev_frontend, dict) else []
        if "pnpm dev --hostname 0.0.0.0" not in " ".join(map(str, command)):
            errors.append("development frontend must expose Next.js HMR")

    required_files = (
        "Dockerfile.backend",
        "Dockerfile.frontend",
        ".dockerignore",
        "compose.ci.yml",
        "scripts/docker/backend-entrypoint.sh",
        "frontend/package.json",
    )
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"Docker runtime asset is missing: {relative}")
    for forbidden in (
        "scripts/docker/neo4j-entrypoint.sh",
        "scripts/docker/postgresql-entrypoint.sh",
        "compose.in-process.yml",
        "compose.neo4j.yml",
    ):
        if (root / forbidden).exists():
            errors.append(f"legacy server runtime asset must be removed: {forbidden}")
    return errors


def validate_ci_compose(document: Any) -> list[str]:
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        return ["CI Compose config is not an object with services"]
    services: dict[str, Any] = document["services"]
    errors: list[str] = []
    if set(services) != EXPECTED_SERVICES:
        return ["CI Compose must resolve only backend and frontend"]
    backend = services.get("backend", {})
    if not str(backend.get("image", "")).startswith("angmoo-backend-ci:"):
        errors.append("CI backend must use the locally built backend image")
    if backend.get("pull_policy") != "never":
        errors.append("CI backend must not pull an unverified registry image")
    frontend = services.get("frontend", {})
    if not str(frontend.get("image", "")).startswith("angmoo-frontend-ci:"):
        errors.append("CI frontend must use the locally built frontend image")
    if frontend.get("pull_policy") != "never":
        errors.append("CI frontend must not pull an unverified registry image")
    return errors


def _resolved(root: Path, files: list[str]) -> dict[str, Any]:
    command = ["docker", "compose"]
    for file in files:
        command.extend(("-f", file))
    command.extend(("config", "--format", "json"))
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "docker compose config failed")
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    try:
        release = _resolved(root, ["compose.yml"])
        development = _resolved(root, ["compose.yml", "compose.dev.yml"])
        continuous_integration = _resolved(root, ["compose.yml", "compose.ci.yml"])
        errors = validate_resolved_compose(release, development, root=root)
        errors.extend(validate_ci_compose(continuous_integration))
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        errors = [f"Docker runtime assets cannot be resolved: {exc}"]
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Docker embedded runtime assets passed: services=2 host_ports=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
