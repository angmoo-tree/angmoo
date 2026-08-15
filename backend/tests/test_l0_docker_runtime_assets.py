from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/check_docker_runtime_assets.py"
SPEC = importlib.util.spec_from_file_location("check_docker_runtime_assets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def _compose(*files: str) -> dict[str, object]:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is required for resolved Compose asset tests")
    command = ["docker", "compose"]
    for file in files:
        command.extend(("-f", file))
    command.extend(("config", "--format", "json"))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def _configs() -> tuple[dict[str, object], dict[str, object]]:
    return _compose("compose.yml"), _compose("compose.yml", "compose.dev.yml")

def _ci_config() -> dict[str, object]:
    return _compose("compose.yml", "compose.ci.yml")


def test_repository_docker_runtime_assets_pass() -> None:
    release, development = _configs()
    assert CHECKER.validate_resolved_compose(release, development, root=ROOT) == []


def test_backend_entrypoint_runs_schema_and_credential_migrations() -> None:
    content = (ROOT / "scripts/docker/backend-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "prepare_database()" in content
    assert "alembic upgrade head" in content
    assert "python -m scripts.migrate_local_credentials" in content
    assert 'APP_SECRET_FILE="$secret_dir/app_secret"' in content
    assert "export APP_SECRET " not in content
    assert 'APP_SECRET="$(cat' not in content
    assert content.index("alembic upgrade head") < content.index(
        "python -m scripts.migrate_local_credentials"
    )


def test_existing_database_requires_its_persistent_secrets() -> None:
    content = (ROOT / "scripts/docker/postgresql-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert 'if [ -s "$data_dir/PG_VERSION" ]; then' in content
    assert "credential_recovery_required secret=app_secret" in content
    assert "validate_secret app_secret" in content
    assert 'chown 10001:10001 "$target"' in content
    assert "secret_acl_unsafe secret=app_secret" in content
    assert "secret_volume_unavailable" in content
    assert content.index('if [ -s "$data_dir/PG_VERSION" ]; then') < content.index(
        "create_secret app_secret"
    )


def test_frontend_never_receives_the_runtime_secret_volume() -> None:
    release, _ = _configs()
    assert release["services"]["frontend"].get("volumes", []) == []
    for service_name in ("backend", "scheduler", "projector"):
        mounts = release["services"][service_name]["volumes"]
        assert any(
            mount.get("target") == "/run/angmoo-secrets"
            and mount.get("read_only") is True
            for mount in mounts
        )


def test_runtime_assets_reject_an_extra_host_port() -> None:
    release, development = _configs()
    mutated = deepcopy(release)
    mutated["services"]["backend"]["ports"] = [
        {"host_ip": "127.0.0.1", "target": 8080, "published": "8080"}
    ]
    assert (
        "only frontend may publish a host port: backend"
        in CHECKER.validate_resolved_compose(mutated, development, root=ROOT)
    )


def test_runtime_assets_reject_plaintext_secret_environment() -> None:
    release, development = _configs()
    mutated = deepcopy(release)
    mutated["services"]["backend"]["environment"]["APP_SECRET"] = "unsafe"
    assert (
        "plaintext runtime secret environment is forbidden: backend"
        in CHECKER.validate_resolved_compose(mutated, development, root=ROOT)
    )


def test_runtime_assets_require_compose_watch() -> None:
    release, development = _configs()
    mutated = deepcopy(development)
    del mutated["services"]["frontend"]["develop"]
    assert (
        "Compose Watch is missing: frontend"
        in CHECKER.validate_resolved_compose(release, mutated, root=ROOT)
    )

def test_ci_compose_reuses_only_locally_built_application_images() -> None:
    assert CHECKER.validate_ci_compose(_ci_config()) == []


def test_ci_compose_rejects_registry_pull_for_frontend() -> None:
    mutated = deepcopy(_ci_config())
    mutated["services"]["frontend"]["pull_policy"] = "missing"
    assert (
        "CI frontend must not pull an unverified registry image"
        in CHECKER.validate_ci_compose(mutated)
    )
