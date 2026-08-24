"""Run the clean-clone and restart smoke for the two-service embedded stack."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SERVICES = {"backend", "frontend"}
EMBEDDED_VOLUME = "angmoo_contributor_embedded_data"


def classify_runtime_failure(text: str) -> str:
    lowered = text.lower()
    if "port is already allocated" in lowered or "address already in use" in lowered:
        return "port_conflict"
    if "docker: not found" in lowered or "cannot connect to the docker" in lowered:
        return "container_engine_unavailable"
    if "manifest unknown" in lowered or "pull access denied" in lowered:
        return "image_pull_failed"
    if "build" in lowered and "failed" in lowered:
        return "image_build_failed"
    return "runtime_state_stale"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class ComposeHarness:
    def __init__(self, *, project: str, tag: str, port: int) -> None:
        self.project = project
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "ANGMOO_CI_IMAGE_TAG": tag,
                "ANGMOO_PORT": str(port),
                "COMPOSE_PROJECT_NAME": project,
            }
        )
        self.prefix = [
            "docker",
            "compose",
            "--project-name",
            project,
            "-f",
            "compose.yml",
            "-f",
            "compose.ci.yml",
        ]

    def run(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [*self.prefix, *arguments],
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if check and completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            category = classify_runtime_failure(detail)
            raise RuntimeError(f"{category}: {detail}")
        return completed

    def cleanup(self, *, volumes: bool) -> None:
        arguments = ["down", "--remove-orphans"]
        if volumes:
            arguments.append("--volumes")
        self.run(*arguments, check=False)


def _service_names(harness: ComposeHarness) -> set[str]:
    payload = harness.run("ps", "--all", "--format", "json").stdout.strip()
    if not payload:
        return set()
    try:
        document: Any = json.loads(payload)
        rows = document if isinstance(document, list) else [document]
    except json.JSONDecodeError:
        # Docker Compose on Windows Desktop emits one JSON object per line,
        # while the Linux plugin used by Hosted CI returns a JSON array.
        rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    return {str(row.get("Service")) for row in rows if isinstance(row, dict)}


def _runtime_health(harness: ComposeHarness) -> dict[str, Any]:
    command = (
        "import json,urllib.request; "
        "print(json.dumps(json.load(urllib.request.urlopen("
        "'http://127.0.0.1:8080/health',timeout=5))))"
    )
    output = harness.run("exec", "-T", "backend", "python", "-c", command).stdout
    payload = json.loads(output)
    assert payload["status"] == "ok"
    assert payload["profile"] == "CONTRIBUTOR_EMBEDDED"
    assert payload["persistence"] == "sqlite"
    assert payload["graph"] == "ladybug"
    assert payload["components"] == {"scheduler": "ready", "projector": "ready"}
    return payload


def _secret_digest(harness: ComposeHarness) -> str:
    command = (
        "from hashlib import sha256; from pathlib import Path; "
        "print(sha256(Path('/var/lib/angmoo/secrets/app-secret').read_bytes()).hexdigest())"
    )
    return harness.run("exec", "-T", "backend", "python", "-c", command).stdout.strip()


def _provider_call_count(harness: ComposeHarness) -> int:
    output = harness.run(
        "exec",
        "-T",
        "backend",
        "/usr/local/bin/angmoo-backend-entrypoint",
        "contributor-diagnostics",
    ).stdout
    payload = json.loads(output)
    assert payload["runtime_profile"] == "CONTRIBUTOR_EMBEDDED"
    assert payload["persistence_provider"] == "sqlite"
    assert payload["graph_provider"] == "ladybug"
    return int(payload["provider_usage"]["recent_call_count"])


def _write_sqlite_marker(harness: ComposeHarness, marker: str) -> None:
    command = (
        "import sqlite3; "
        "p='/var/lib/angmoo/canonical/generations/contributor-v1/angmoo.sqlite3'; "
        "c=sqlite3.connect(p); "
        "c.execute(\"INSERT INTO site_operation_settings"
        "(key,value,updated_by_user_id,updated_at) VALUES (?, ?, NULL, CURRENT_TIMESTAMP)\", "
        f"({marker!r}, {marker!r})); "
        "c.commit(); c.close()"
    )
    harness.run("exec", "-T", "backend", "python", "-c", command)


def _sqlite_marker_exists(harness: ComposeHarness, marker: str) -> bool:
    command = (
        "import sqlite3; "
        "p='/var/lib/angmoo/canonical/generations/contributor-v1/angmoo.sqlite3'; "
        "c=sqlite3.connect(p); "
        f"print(c.execute('SELECT COUNT(*) FROM site_operation_settings WHERE key=? AND value=?', ({marker!r}, {marker!r})).fetchone()[0]); "
        "c.close()"
    )
    return harness.run("exec", "-T", "backend", "python", "-c", command).stdout.strip() == "1"


def _delete_sqlite_marker(harness: ComposeHarness, marker: str) -> None:
    command = (
        "import sqlite3; "
        "p='/var/lib/angmoo/canonical/generations/contributor-v1/angmoo.sqlite3'; "
        "c=sqlite3.connect(p); "
        f"c.execute('DELETE FROM site_operation_settings WHERE key=?', ({marker!r},)); "
        "c.commit(); c.close()"
    )
    harness.run("exec", "-T", "backend", "python", "-c", command)


def run_smoke(*, tag: str, project: str, port: int) -> None:
    harness = ComposeHarness(project=project, tag=tag, port=port)
    harness.cleanup(volumes=True)
    try:
        harness.run("up", "-d", "--wait", "--wait-timeout", "300")
        if _service_names(harness) != EXPECTED_SERVICES:
            raise RuntimeError("runtime_state_stale: two-service topology mismatch")
        _runtime_health(harness)
        if _provider_call_count(harness) != 0:
            raise RuntimeError("provider_call_regression: fresh Browser Run called a provider")
        digest_before = _secret_digest(harness)
        marker = f"browser-run-{uuid.uuid4().hex}"
        _write_sqlite_marker(harness, marker)
        volumes = harness.run("config", "--volumes").stdout.splitlines()
        if EMBEDDED_VOLUME not in volumes:
            raise RuntimeError("runtime_state_stale: embedded volume missing")

        harness.run("stop", "--timeout", "30")
        harness.run("up", "-d", "--wait", "--wait-timeout", "300")
        _runtime_health(harness)
        if not _sqlite_marker_exists(harness, marker):
            raise RuntimeError("sqlite_write_lost: canonical marker did not survive restart")
        _delete_sqlite_marker(harness, marker)
        if _provider_call_count(harness) != 0:
            raise RuntimeError("provider_call_regression: restart called a provider")
        digest_after = _secret_digest(harness)
        if digest_after != digest_before:
            raise RuntimeError("secret_mismatch: APP_SECRET changed after restart")
        print(
            "Embedded container smoke passed: "
            f"services=2 volume={EMBEDDED_VOLUME} sqlite_write_stable=true "
            "ladybug_ready=true scheduler_ready=true projector_ready=true "
            "provider_calls=0 restart_secret_stable=true"
        )
    except (AssertionError, json.JSONDecodeError, OSError, RuntimeError) as exc:
        completed = harness.run(
            "logs", "--no-color", "--tail", "200", check=False
        )
        logs = (completed.stdout or completed.stderr).strip()
        detail = logs if logs else "compose logs unavailable"
        raise RuntimeError(f"{exc}; compose_logs={detail}") from exc
    finally:
        harness.cleanup(volumes=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    try:
        run_smoke(
            tag=args.tag,
            project=args.project,
            port=args.port or _free_port(),
        )
    except (AssertionError, json.JSONDecodeError, OSError, RuntimeError) as exc:
        print(f"container smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
