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


def test_repository_docker_runtime_assets_pass() -> None:
    release, development = _configs()
    assert CHECKER.validate_resolved_compose(release, development, root=ROOT) == []


def test_backend_entrypoint_exposes_migration_mode() -> None:
    content = (ROOT / "scripts/docker/backend-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "  migrate)\n    exec alembic upgrade head\n    ;;" in content


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