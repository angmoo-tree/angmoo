"""Linux host process ownership. No DB access or machine-wide process cleanup."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request

from payload import require


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def identity(pid: int) -> dict:
    # comm may contain spaces and parentheses. Fields after the final ')' are
    # state (3) through starttime (22); PID alone never proves ownership.
    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "start_ticks": stat[19], "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}


def alive(record: dict) -> bool:
    try:
        return identity(record["pid"]) == record and Path(f"/proc/{record['pid']}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, ValueError, KeyError, IndexError):
        return False


def free_port(port: int) -> None:
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            raise ValueError("port_in_use") from exc


def ready(url: str, source: str, nonce: str, *, backend: bool) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read(65537))
        return payload.get("source_sha") == source and payload.get("launch_id") == nonce and payload.get("version") == "0.1.0" and (not backend or payload.get("status") == "ok" and payload.get("persistence") == "sqlite" and payload.get("graph") == "ladybug")
    except (OSError, ValueError):
        return False


def stop_child(process: subprocess.Popen, record: dict, grace: float) -> None:
    if process.poll() is not None:
        return
    require(alive(record) and os.getpgid(process.pid) == process.pid, "process_ownership_changed")
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        require(alive(record) and os.getpgid(process.pid) == process.pid, "process_ownership_changed")
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def await_ready(process, url, source, nonce, *, backend, timeout=180, cancelled=lambda: False):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        require(not cancelled(), "start_cancelled")
        require(process.poll() is None, "service_exited_before_ready")
        if ready(url, source, nonce, backend=backend):
            return
        time.sleep(0.5)
    raise ValueError("service_readiness_timeout")
