"""Run the isolated L0 full-stack, reduced-mode, and lifecycle fixtures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
FULL_SERVICES = {
    "backend",
    "frontend",
    "neo4j",
    "postgresql",
    "projector",
    "scheduler",
}
CORE_SERVICES = {"backend", "frontend", "postgresql"}
AUTONOMY_SERVICES = {"backend", "frontend", "postgresql", "scheduler"}
PROVIDER_MARKERS = (
    "generativelanguage.googleapis.com",
    "api.pollinations.ai",
    "gen.pollinations.ai",
    "api.replicate.com",
)
L3_PREVIOUS_REVISION = "20260816_0080"


def classify_runtime_failure(message: str) -> str:
    lowered = message.lower()
    if any(
        marker in lowered
        for marker in (
            "address already in use",
            "bind for 127.0.0.1",
            "port is already allocated",
            "ports are not available",
        )
    ):
        return "port_conflict"
    if any(
        marker in lowered
        for marker in ("docker: not found", "no such file or directory: 'docker'", "executable file not found")
    ):
        return "container_engine_unavailable"
    if any(
        marker in lowered
        for marker in ("pull access denied", "manifest unknown", "not found: manifest")
    ):
        return "image_pull_failed"
    if any(marker in lowered for marker in ("no space left on device", "read-only file system")):
        return "data_path_unwritable"
    return "runtime_state_stale"


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{classify_runtime_failure(detail)}: {' '.join(command)}: {detail}")
    return completed


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def preflight() -> str:
    if shutil.which("docker") is None:
        raise RuntimeError("container_engine_unavailable: Docker CLI was not found")
    version = _run(["docker", "compose", "version", "--short"]).stdout.strip()
    if _version_tuple(version) < (2, 22, 0):
        raise RuntimeError(
            f"unsupported_tool_version: Docker Compose {version!r}; expected >=2.22.0"
        )
    _run(["docker", "info"])
    return version


class ComposeHarness:
    def __init__(self, *, project: str, tag: str, port: int) -> None:
        self.project = project
        self.tag = tag
        self.port = port
        self.env = os.environ.copy()
        self.env["ANGMOO_CI_IMAGE_TAG"] = tag
        self.env["ANGMOO_PORT"] = str(port)
        self.base = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            "compose.yml",
            "-f",
            "compose.ci.yml",
        ]

    def run(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return _run([*self.base, *arguments], env=self.env, check=check)

    def cleanup(self, *, volumes: bool) -> None:
        arguments = ["down", "--remove-orphans"]
        if volumes:
            arguments.append("--volumes")
        self.run(*arguments, check=False)

    def _ps(self) -> list[dict[str, Any]]:
        output = self.run("ps", "--all", "--format", "json").stdout.strip()
        if not output:
            return []
        if output.startswith("["):
            payload = json.loads(output)
            return payload if isinstance(payload, list) else []
        return [json.loads(line) for line in output.splitlines() if line.strip()]

    def wait_healthy(self, expected: set[str], timeout: int = 300) -> None:
        deadline = time.monotonic() + timeout
        last: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            last = self._ps()
            by_service = {str(item.get("Service")): item for item in last}
            if set(by_service) == expected and all(
                str(by_service[name].get("State", "")).lower() == "running"
                and str(by_service[name].get("Health", "")).lower() == "healthy"
                for name in expected
            ):
                return
            time.sleep(2)
        raise RuntimeError(
            "runtime_state_stale: services did not become healthy: "
            + json.dumps(last, sort_keys=True)
        )

    def container_ids(self, services: set[str]) -> dict[str, str]:
        return {
            service: self.run("ps", "-q", service).stdout.strip()
            for service in sorted(services)
        }

    def exec(self, service: str, *command: str) -> str:
        return self.run("exec", "-T", service, *command).stdout.strip()


def _check_frontend(port: int) -> None:
    with urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"runtime_state_stale: frontend returned {response.status}")


def _check_provider_calls(logs: str) -> None:
    lowered = logs.lower()
    matches = [marker for marker in PROVIDER_MARKERS if marker in lowered]
    if matches:
        raise RuntimeError(f"provider real call marker found in container logs: {matches}")


def _l3_canonical_digest(harness: ComposeHarness) -> str:
    return harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        "SELECT concat_ws('|',"
        "(SELECT count(*) FROM worlds),"
        "coalesce((SELECT md5(string_agg(id, ',' ORDER BY id)) FROM worlds), ''),"
        "(SELECT count(*) FROM characters),"
        "coalesce((SELECT md5(string_agg(id, ',' ORDER BY id)) FROM characters), ''),"
        "(SELECT count(*) FROM world_characters),"
        "coalesce((SELECT md5(string_agg(id, ',' ORDER BY id)) FROM world_characters), ''),"
        "(SELECT count(*) FROM posts),"
        "coalesce((SELECT md5(string_agg(id, ',' ORDER BY id)) FROM posts), '')"
        ");",
    )


def _run_backend_alembic(harness: ComposeHarness, *arguments: str) -> None:
    command = (
        'postgresql_password="$(cat /run/angmoo-secrets/postgresql_password)"; '
        'export DATABASE_URL="postgresql+psycopg://angmoo:'
        '${postgresql_password}@postgresql:5432/angmoo"; '
        f"exec alembic {' '.join(arguments)}"
    )
    harness.run(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "sh",
        "backend",
        "-c",
        command,
    )


def _l3_migration_round_trip(
    harness: ComposeHarness,
    *,
    migration_head: str,
) -> None:
    unsupported_rows = harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        "SELECT "
        "(SELECT count(*) FROM world_characters "
        " WHERE control_mode = 'owner_controlled') + "
        "(SELECT count(*) FROM owner_manual_social_writes) + "
        "(SELECT count(*) FROM owner_manual_inbox_candidates);",
    )
    if unsupported_rows != "0":
        raise RuntimeError(
            "runtime_state_stale: clean-clone migration fixture contains "
            f"non-downgradable L3 rows={unsupported_rows}"
        )

    digest_before = _l3_canonical_digest(harness)
    harness.run("stop", "frontend", "projector", "scheduler", "backend")
    _run_backend_alembic(harness, "downgrade", L3_PREVIOUS_REVISION)
    downgraded_revision = harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        "SELECT version_num FROM alembic_version;",
    )
    if downgraded_revision != L3_PREVIOUS_REVISION:
        raise RuntimeError(
            "runtime_state_stale: L3 downgrade revision mismatch "
            f"database={downgraded_revision} expected={L3_PREVIOUS_REVISION}"
        )

    _run_backend_alembic(harness, "upgrade", "head")
    upgraded_revision = harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        "SELECT version_num FROM alembic_version;",
    )
    digest_after = _l3_canonical_digest(harness)
    if upgraded_revision != migration_head or digest_after != digest_before:
        raise RuntimeError(
            "runtime_state_stale: L3 migration round trip changed canonical data "
            f"revision={upgraded_revision} expected={migration_head} "
            f"digest_before={digest_before} digest_after={digest_after}"
        )

    unknown_modes = harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        "SELECT count(*) FROM world_characters "
        "WHERE control_mode IS NULL OR control_mode <> 'autonomous' "
        "OR owner_user_id IS NOT NULL;",
    )
    if unknown_modes != "0":
        raise RuntimeError(
            "runtime_state_stale: autonomous backfill parity failed "
            f"unexpected_world_characters={unknown_modes}"
        )
    print(
        "L3 migration round trip passed: "
        f"{migration_head}->{L3_PREVIOUS_REVISION}->{migration_head} "
        f"canonical_digest={digest_after}"
    )
    harness.run("up", "-d")
    harness.wait_healthy(FULL_SERVICES)


def _full_stack_lifecycle(harness: ComposeHarness) -> None:
    harness.run("up", "-d")
    harness.wait_healthy(FULL_SERVICES)
    _check_frontend(harness.port)
    harness.exec(
        "backend",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)",
    )
    migration_head = harness.exec("backend", "alembic", "heads").split()[0]
    database_revision = harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        "SELECT version_num FROM alembic_version;",
    )
    if database_revision != migration_head:
        raise RuntimeError(
            "runtime_state_stale: migration head mismatch "
            f"database={database_revision} source={migration_head}"
        )
    print(f"migration head passed: revision={database_revision}")

    _l3_migration_round_trip(harness, migration_head=migration_head)

    first_ids = harness.container_ids(FULL_SERVICES)
    harness.run("up", "-d")
    harness.wait_healthy(FULL_SERVICES)
    second_ids = harness.container_ids(FULL_SERVICES)
    if first_ids != second_ids:
        raise RuntimeError("runtime_state_stale: repeated start replaced a container")

    marker = f"{harness.project}-persisted"
    harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "CREATE TABLE IF NOT EXISTS l0_runtime_markers (marker text PRIMARY KEY);",
    )
    harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        f"INSERT INTO l0_runtime_markers(marker) VALUES ('{marker}') ON CONFLICT DO NOTHING;",
    )
    secret_before = harness.exec(
        "postgresql", "sh", "-c", "sha256sum /run/angmoo-secrets/app_secret | cut -d ' ' -f1"
    )
    _check_provider_calls(harness.run("logs", "--no-color").stdout)

    harness.cleanup(volumes=False)
    harness.run("up", "-d")
    harness.wait_healthy(FULL_SERVICES)
    persisted = harness.exec(
        "postgresql",
        "psql",
        "-U",
        "angmoo",
        "-d",
        "angmoo",
        "-Atc",
        f"SELECT count(*) FROM l0_runtime_markers WHERE marker='{marker}';",
    )
    secret_after = harness.exec(
        "postgresql", "sh", "-c", "sha256sum /run/angmoo-secrets/app_secret | cut -d ' ' -f1"
    )
    if persisted != "1" or secret_before != secret_after:
        raise RuntimeError("runtime_state_stale: data or runtime secret was not preserved")
    _check_frontend(harness.port)


def _reduced_modes(harness: ComposeHarness) -> None:
    for name, services in (("core", CORE_SERVICES), ("autonomy", AUTONOMY_SERVICES)):
        harness.cleanup(volumes=False)
        harness.run("up", "-d", *sorted(services))
        harness.wait_healthy(services)
        running = {
            line.strip()
            for line in harness.run("ps", "--services", "--status", "running").stdout.splitlines()
            if line.strip()
        }
        if running != services:
            raise RuntimeError(
                f"runtime_state_stale: {name} mode services={sorted(running)} expected={sorted(services)}"
            )


def _port_conflict(harness: ComposeHarness) -> None:
    harness.cleanup(volumes=False)
    holder = f"{harness.project}-port-holder"
    backend_image = f"angmoo-backend-ci:{harness.tag}"
    _run(["docker", "rm", "-f", holder], check=False)
    try:
        _run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                holder,
                "-p",
                f"127.0.0.1:{harness.port}:8080",
                "--entrypoint",
                "python",
                backend_image,
                "-m",
                "http.server",
                "8080",
            ]
        )
        attempt = harness.run("up", "-d", "frontend", check=False)
        if attempt.returncode == 0:
            raise RuntimeError("port_conflict fixture unexpectedly started frontend")
        message = attempt.stderr or attempt.stdout
        if classify_runtime_failure(message) != "port_conflict":
            raise RuntimeError(f"port conflict was misclassified: {message.strip()}")
        print("port_conflict fixture passed: automatic port move=0 process kill=0")
    finally:
        harness.cleanup(volumes=False)
        _run(["docker", "rm", "-f", holder], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--project", default="angmoo-l0-container-smoke")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    harness = ComposeHarness(project=args.project, tag=args.tag, port=args.port)
    try:
        compose_version = preflight()
        harness.cleanup(volumes=True)
        _full_stack_lifecycle(harness)
        _reduced_modes(harness)
        _port_conflict(harness)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        print(harness.run("logs", "--no-color", check=False).stdout, file=sys.stderr)
        return 1
    finally:
        harness.cleanup(volumes=True)
    print(
        "L0 container smoke passed: full=6 core=3 autonomy=4 "
        f"compose={compose_version} provider_calls=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
