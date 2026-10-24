"""Linux host process ownership. No DB access or machine-wide process cleanup."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import urllib.request
import urllib.error

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


def proc_bytes(path: Path, limit: int) -> bytes:
    """Bound a procfs read even when its reported file size is zero."""
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    require(len(value) <= limit, "process_observation_limit")
    return value


def proc_stat(path: Path) -> tuple[dict, str, int]:
    fields = proc_bytes(path / "stat", 8192).decode().rsplit(")", 1)[1].split()
    record = {"pid": int(path.name), "start_ticks": fields[19]}
    require(record["start_ticks"].isdigit(), "process_observation_invalid")
    return record, fields[0], int(fields[3])


def valid_identity(record) -> bool:
    return (isinstance(record, dict) and type(record.get("pid")) is int and record["pid"] > 0
            and isinstance(record.get("start_ticks"), str) and record["start_ticks"].isdigit()
            and isinstance(record.get("boot_id"), str)
            and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", record["boot_id"]) is not None)


def observe_identity(record, *, proc=Path("/proc")) -> dict:
    """Deletion/recovery needs positive absence evidence, unlike a liveness hint.

    A stable reused PID is gone; identity changing *during* an observation is
    unknown. This API never signals a process and does not change alive().
    """
    if not valid_identity(record):
        return {"status": "unknown", "basis": "invalid_identity"}
    try:
        boot = proc_bytes(proc / "sys/kernel/random/boot_id", 128).decode().strip()
    except (OSError, ValueError, UnicodeError):
        return {"status": "unknown", "basis": "boot_unreadable"}
    try:
        if boot != record["boot_id"]:
            require(bool(re.fullmatch(r"[0-9a-f-]{36}", boot)), "process_observation_invalid")
            return {"status": "gone", "basis": "different_boot"}
        path = proc / str(record["pid"])
        first, state, _ = proc_stat(path)
        second, _, _ = proc_stat(path)
        if first != second:
            return {"status": "unknown", "basis": "identity_changed"}
        if first["start_ticks"] != record["start_ticks"]:
            return {"status": "gone", "basis": "pid_reused"}
        return {"status": "gone" if state == "Z" else "alive", "basis": "zombie" if state == "Z" else "matching_identity"}
    except (FileNotFoundError, ProcessLookupError):
        return {"status": "gone", "basis": "process_absent"}
    except (OSError, ValueError, IndexError, UnicodeError):
        return {"status": "unknown", "basis": "process_unreadable"}


def free_port(port: int) -> None:
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            raise ValueError("port_in_use") from exc


def probe_ready(url: str, source: str, nonce: str, *, expected_version: str, backend: bool) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return {"ready": False, "code": "response_too_large"}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return {"ready": False, "code": "invalid_json_shape"}
        for key, expected in (("source_sha", source), ("launch_id", nonce), ("version", expected_version)):
            if payload.get(key) != expected:
                return {"ready": False, "code": key + "_mismatch"}
        if backend and (payload.get("status"), payload.get("persistence"), payload.get("graph")) != ("ok", "sqlite", "ladybug"):
            return {"ready": False, "code": "backend_not_ready"}
        return {"ready": True, "code": "ready"}
    except urllib.error.HTTPError as exc:
        return {"ready": False, "code": "http_status", "http_status": exc.code}
    except urllib.error.URLError as exc:
        reason = exc.reason
        return {"ready": False, "code": "timeout" if isinstance(reason, TimeoutError) else "connection_error",
                "exception_type": type(reason).__name__, "errno": getattr(reason, "errno", None)}
    except TimeoutError:
        return {"ready": False, "code": "timeout"}
    except ValueError:
        return {"ready": False, "code": "invalid_json"}
    except OSError as exc:
        return {"ready": False, "code": "io_error", "exception_type": type(exc).__name__, "errno": exc.errno}


def ready(url: str, source: str, nonce: str, *, expected_version: str, backend: bool) -> bool:
    return probe_ready(url, source, nonce, expected_version=expected_version, backend=backend)["ready"]


def session_members(record: dict) -> list[dict]:
    """Observe live descendants in the private session, including orphans.

    A session ID cannot be reused while its group survives. Check boot and
    creation order too; never signal a PID merely because it has an old number.
    """
    if record.get("boot_id") != Path("/proc/sys/kernel/random/boot_id").read_text().strip():
        return []  # no process from the old boot can survive
    try:
        if identity(record["pid"]) != record:
            return []  # PID reuse proves this is not the old private session
    except FileNotFoundError:
        pass  # the original session leader may already have exited
    members = []
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            stat = path.read_text().rsplit(")", 1)[1].split()
            if stat[0] == "Z" or int(stat[3]) != record["pid"]:
                continue
            require(int(stat[19]) >= int(record["start_ticks"]), "process_ownership_changed")
            members.append(identity(int(path.parent.name)))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return members


def stop_child(process: subprocess.Popen, record: dict, grace: float) -> None:
    if process.poll() is None:
        require(alive(record) and os.getsid(process.pid) == process.pid, "process_ownership_changed")
    # The PRoot parent can exit before a worker. Waiting only for that parent
    # would leave a second scheduler/search child alive on the next start.
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 10)):
        members = session_members(record)
        if not members:
            process.wait(timeout=1)
            return
        for member in members:
            if alive(member):
                try:
                    os.kill(member["pid"], sig)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            process.poll()
            if not session_members(record):
                process.wait(timeout=1)
                return
            time.sleep(0.05)
    raise ValueError("owned_process_stop_failed")


def await_ready(process, url, source, nonce, *, expected_version, backend, timeout=180, cancelled=lambda: False, observe=lambda value: None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        require(not cancelled(), "start_cancelled")
        require(process.poll() is None, "service_exited_before_ready")
        probe = probe_ready(url, source, nonce, expected_version=expected_version, backend=backend)
        observe(probe)
        if probe["ready"]:
            return
        time.sleep(0.5)
    raise ValueError("service_readiness_timeout")
