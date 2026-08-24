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


def test_backend_entrypoint_uses_only_typed_embedded_runtime() -> None:
    content = (ROOT / "scripts/docker/backend-entrypoint.sh").read_text("utf-8")
    assert "contributor-api|contributor-api-dev" in content
    assert "app.runtime.contributor_backend" in content
    assert "ANGMOO_CONTRIBUTOR_DATA_ROOT" in content
    for legacy in (
        "postgresql_password",
        "neo4j_password",
        "DATABASE_URL=",
        "run_resident_tick_scheduler",
    ):
        assert legacy not in content


def test_frontend_never_receives_embedded_data_volume() -> None:
    release, _ = _configs()
    assert release["services"]["frontend"].get("volumes", []) == []
    mounts = release["services"]["backend"]["volumes"]
    assert any(mount.get("target") == "/var/lib/angmoo" for mount in mounts)


def test_runtime_assets_reject_an_extra_host_port() -> None:
    release, development = _configs()
    mutated = deepcopy(release)
    mutated["services"]["backend"]["ports"] = [
        {"host_ip": "127.0.0.1", "target": 8080, "published": "8080"}
    ]
    assert "only frontend may publish a host port: backend" in CHECKER.validate_resolved_compose(
        mutated, development, root=ROOT
    )


def test_runtime_assets_reject_legacy_runtime_environment() -> None:
    release, development = _configs()
    mutated = deepcopy(release)
    mutated["services"]["backend"]["environment"]["DATABASE_URL"] = "postgresql://unsafe"
    assert "plaintext or legacy runtime environment is forbidden: backend" in CHECKER.validate_resolved_compose(
        mutated, development, root=ROOT
    )


def test_runtime_assets_require_compose_watch() -> None:
    release, development = _configs()
    mutated = deepcopy(development)
    del mutated["services"]["frontend"]["develop"]
    assert "Compose Watch is missing: frontend" in CHECKER.validate_resolved_compose(
        release, mutated, root=ROOT
    )


def test_ci_compose_reuses_only_locally_built_application_images() -> None:
    assert CHECKER.validate_ci_compose(
        _compose("compose.yml", "compose.ci.yml")
    ) == []


def test_container_smoke_accepts_windows_compose_ndjson() -> None:
    smoke_path = ROOT / "scripts/ci/run_l0_container_smoke.py"
    spec = importlib.util.spec_from_file_location("run_l0_container_smoke", smoke_path)
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)

    class Harness:
        @staticmethod
        def run(*_arguments: str):
            return type(
                "Result",
                (),
                {
                    "stdout": (
                        '{"Service":"backend"}\n'
                        '{"Service":"frontend"}\n'
                    )
                },
            )()

    assert smoke._service_names(Harness()) == {"backend", "frontend"}


def test_container_smoke_reads_the_canonical_app_secret_path() -> None:
    content = (ROOT / "scripts/ci/run_l0_container_smoke.py").read_text("utf-8")
    assert "/var/lib/angmoo/secrets/app-secret" in content
    assert "/var/lib/angmoo/secrets/app_secret" not in content
    assert "site_operation_settings" in content
    assert "CREATE TABLE" not in content
    assert "sqlite_write_stable=true" in content
    assert "ladybug_ready=true" in content
    assert "provider_calls=0" in content
    assert "contributor-diagnostics" in content
    assert "compose_logs=" in content
