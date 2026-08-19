from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _start_sidecar(
    executable: Path,
    *,
    parent_pid: int,
    token: str,
    lock_path: Path,
    graph_path: Path,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            str(executable),
            "--auth-token",
            token,
            "--parent-pid",
            str(parent_pid),
            "--lock-file",
            str(lock_path),
            "--graph-path",
            str(graph_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _first_event(process: subprocess.Popen[str]) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeError("sidecar_stdout_unavailable")
    line = process.stdout.readline().strip()
    if not line:
        stderr = process.stderr.read().strip() if process.stderr else ""
        raise RuntimeError(f"sidecar_ready_missing:{process.poll()}:{stderr}")
    return json.loads(line)


def _request(port: int, path: str, token: str | None, method: str = "GET") -> int:
    headers = {"X-Angmoo-Spike-Token": token} if token else {}
    request = Request(f"http://127.0.0.1:{port}{path}", headers=headers, method=method)
    try:
        with urlopen(request, timeout=3) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)


def run_probe(executable: Path, data_root: Path) -> dict[str, Any]:
    data_root = data_root.resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    lock_path = data_root / "duplicate.writer.lock"
    graph_path = data_root / "duplicate-graph.lbdb"
    token = secrets.token_hex(24)
    primary = _start_sidecar(
        executable,
        parent_pid=os.getpid(),
        token=token,
        lock_path=lock_path,
        graph_path=graph_path,
    )
    try:
        ready = _first_event(primary)
        if ready.get("event") != "ready":
            raise RuntimeError(f"primary_not_ready:{ready}")
        port = int(ready["port"])
        unauthenticated_rejected = _request(port, "/health", None) == 401
        authenticated_health = _request(port, "/health", token) == 200

        duplicate = _start_sidecar(
            executable,
            parent_pid=os.getpid(),
            token=secrets.token_hex(24),
            lock_path=lock_path,
            graph_path=graph_path,
        )
        duplicate_event = _first_event(duplicate)
        duplicate_exit = duplicate.wait(timeout=10)
        duplicate_blocked = (
            duplicate_exit == 17
            and duplicate_event.get("event") == "fatal"
            and duplicate_event.get("error_class") == "writer_lock_unavailable"
        )

        graceful_shutdown = _request(port, "/shutdown", token, method="POST") == 200
        primary_exit = primary.wait(timeout=10)
        graceful_exit = graceful_shutdown and primary_exit == 0
    finally:
        if primary.poll() is None:
            primary.kill()
            primary.wait(timeout=5)

    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    orphan = _start_sidecar(
        executable,
        parent_pid=sentinel.pid,
        token=secrets.token_hex(24),
        lock_path=data_root / "orphan.writer.lock",
        graph_path=data_root / "orphan-graph.lbdb",
    )
    try:
        orphan_ready = _first_event(orphan).get("event") == "ready"
        sentinel.terminate()
        sentinel.wait(timeout=5)
        started = time.perf_counter()
        orphan_exit = orphan.wait(timeout=10)
        orphan_cleanup_ms = round((time.perf_counter() - started) * 1000, 2)
        orphan_cleanup = orphan_ready and orphan_exit == 0 and orphan_cleanup_ms < 5000
    finally:
        if sentinel.poll() is None:
            sentinel.kill()
            sentinel.wait(timeout=5)
        if orphan.poll() is None:
            orphan.kill()
            orphan.wait(timeout=5)

    evidence = {
        "schema_version": 1,
        "duplicate_writer_blocked": duplicate_blocked,
        "unauthenticated_rejected": unauthenticated_rejected,
        "authenticated_health": authenticated_health,
        "graceful_shutdown": graceful_exit,
        "orphan_cleanup": orphan_cleanup,
        "orphan_cleanup_ms": orphan_cleanup_ms,
        "token_persisted": False,
    }
    evidence["status"] = "PASS" if all(
        (
            duplicate_blocked,
            unauthenticated_rejected,
            authenticated_health,
            graceful_exit,
            orphan_cleanup,
        )
    ) else "FAIL"
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = run_probe(args.sidecar.resolve(), args.data_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
