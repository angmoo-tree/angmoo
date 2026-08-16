"""Validate the resolved L0 Docker Compose topology and image assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SERVICES = {
    "backend",
    "frontend",
    "neo4j",
    "postgresql",
    "projector",
    "scheduler",
}
FORBIDDEN_ENVIRONMENT = {
    "APP_SECRET",
    "DATABASE_URL",
    "NEO4J_AUTH",
    "NEO4J_PASSWORD",
    "POSTGRES_PASSWORD",
}
EXPECTED_VOLUMES = {
    "angmoo_media",
    "angmoo_neo4j_data",
    "angmoo_neo4j_logs",
    "angmoo_postgresql_data",
    "angmoo_runtime_secrets",
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
        errors.append("release Compose must contain the complete six-service stack")

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
            errors.append(f"plaintext runtime secret environment is forbidden: {name}")

    postgresql = services.get("postgresql")
    if isinstance(postgresql, dict) and "@sha256:" not in str(
        postgresql.get("image", "")
    ):
        errors.append("PostgreSQL image must be digest pinned")
    neo4j = services.get("neo4j")
    if isinstance(neo4j, dict) and "@sha256:" not in str(neo4j.get("image", "")):
        errors.append("Neo4j image must be digest pinned")

    volumes = release.get("volumes", {})
    if not isinstance(volumes, dict) or set(volumes) != EXPECTED_VOLUMES:
        errors.append("release Compose named volume inventory mismatch")

    if not isinstance(development, dict) or not isinstance(
        development.get("services"), dict
    ):
        errors.append("development Compose config is not an object with services")
    else:
        dev_services: dict[str, Any] = development["services"]
        for name in {"backend", "frontend"}:
            service = dev_services.get(name)
            if not isinstance(service, dict) or not service.get("build"):
                errors.append(f"development service must build locally: {name}")
        backend = dev_services.get("backend")
        backend_image = backend.get("image") if isinstance(backend, dict) else None
        for name in {"scheduler", "projector"}:
            service = dev_services.get(name)
            if (
                not isinstance(service, dict)
                or service.get("image") != backend_image
            ):
                errors.append(f"development worker must reuse backend image: {name}")
            elif service.get("build"):
                errors.append(f"development worker must not duplicate backend build: {name}")
        for name in {"backend", "frontend"}:
            service = dev_services.get(name, {})
            develop = service.get("develop", {}) if isinstance(service, dict) else {}
            if not isinstance(develop, dict) or not develop.get("watch"):
                errors.append(f"Compose Watch is missing: {name}")

    required_files = (
        "Dockerfile.backend",
        "Dockerfile.frontend",
        ".dockerignore",
        "compose.ci.yml",
        "backend/scripts/run_resident_tick_scheduler.py",
        "frontend/package.json",
        "scripts/docker/backend-entrypoint.sh",
        "scripts/docker/neo4j-entrypoint.sh",
        "scripts/docker/postgresql-entrypoint.sh",
    )
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"Docker runtime asset is missing: {relative}")

    for dockerfile in ("Dockerfile.backend", "Dockerfile.frontend"):
        path = root / dockerfile
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if (
                "USER " not in content
                or "org.opencontainers.image.licenses" not in content
            ):
                errors.append(
                    f"runtime image metadata or non-root user is missing: {dockerfile}"
                )
            if dockerfile == "Dockerfile.frontend":
                if "ARG PNPM_VERSION=11.22.0" not in content:
                    errors.append("frontend Dockerfile must pin pnpm 11.22.0")
                if "ENV COREPACK_HOME=/opt/corepack" not in content:
                    errors.append("frontend Dockerfile must share the Corepack cache")
                if "PNPM_HOME=/opt/pnpm" not in content:
                    errors.append("frontend Dockerfile must share the pnpm store")
                if (
                    "COPY --chown=node:node frontend/package.json "
                    "frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./"
                    not in content
                ):
                    errors.append(
                        "frontend dependency manifests must be owned by the node user"
                    )
                if "USER node\nRUN pnpm install --frozen-lockfile" not in content:
                    errors.append(
                        "frontend dependencies must be installed by the runtime node user"
                    )

    frontend_package_path = root / "frontend/package.json"
    if frontend_package_path.is_file():
        try:
            frontend_package = json.loads(
                frontend_package_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            errors.append("frontend package.json is not valid JSON")
        else:
            if frontend_package.get("packageManager") != "pnpm@11.22.0":
                errors.append("frontend packageManager must pin pnpm 11.22.0")

    frontend_next_config_path = root / "frontend/next.config.ts"
    if frontend_next_config_path.is_file():
        frontend_next_config = frontend_next_config_path.read_text(encoding="utf-8")
        if 'allowedDevOrigins: ["127.0.0.1", "localhost"]' not in frontend_next_config:
            errors.append(
                "frontend development server must allow the documented loopback origins"
            )
    return errors


def validate_ci_compose(document: Any) -> list[str]:
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        return ["CI Compose config is not an object with services"]
    services: dict[str, Any] = document["services"]
    errors: list[str] = []
    if set(services) != EXPECTED_SERVICES:
        errors.append("CI Compose must resolve the complete six-service stack")
        return errors
    backend_image = str(services.get("backend", {}).get("image", ""))
    if not backend_image.startswith("angmoo-backend-ci:"):
        errors.append("CI backend must use the locally built backend image")
    for name in ("backend", "scheduler", "projector"):
        service = services.get(name, {})
        if service.get("image") != backend_image or service.get("pull_policy") != "never":
            errors.append(f"CI backend worker image contract mismatch: {name}")
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
    print("L0 Docker runtime assets passed: services=6 host_ports=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
