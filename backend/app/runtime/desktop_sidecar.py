from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False
        return True
    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
        process_query_limited_information, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(  # type: ignore[attr-defined]
            handle, ctypes.byref(exit_code)
        ):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]


class RuntimeOwnership:
    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root
        self.lock_path = runtime_root / "sidecar.owner.json"
        self.endpoint_path = runtime_root / "sidecar.endpoint.json"
        self.pid = os.getpid()

    def acquire(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                existing = json.loads(self.lock_path.read_text(encoding="utf-8"))
                existing_pid = int(existing.get("pid", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                existing_pid = 0
            if _process_alive(existing_pid):
                raise RuntimeError("desktop_sidecar_already_owned")
            self.lock_path.unlink(missing_ok=True)
            self.endpoint_path.unlink(missing_ok=True)
        payload = {"schema_version": 1, "pid": self.pid}
        self.lock_path.write_text(json.dumps(payload), encoding="utf-8")

    def publish_endpoint(self, port: int) -> None:
        payload = {
            "schema_version": 1,
            "pid": self.pid,
            "host": "127.0.0.1",
            "port": port,
        }
        self.endpoint_path.write_text(json.dumps(payload), encoding="utf-8")

    def release(self) -> None:
        try:
            current_owner = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current_owner = {}
        if current_owner.get("pid") == self.pid:
            self.lock_path.unlink(missing_ok=True)

        try:
            current_endpoint = json.loads(
                self.endpoint_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            current_endpoint = {}
        if current_endpoint.get("pid") == self.pid:
            self.endpoint_path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Angmoo packaged desktop sidecar")
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    return parser.parse_args()


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing_{name.lower()}")
    return value


def _watch_parent(parent_pid: int, server: Any) -> None:
    while not server.should_exit:
        if not _process_alive(parent_pid):
            server.should_exit = True
            return
        time.sleep(0.5)


def main() -> int:
    args = _parse_args()
    token = _required_environment("DESKTOP_LAUNCH_TOKEN")
    origin = _required_environment("DESKTOP_ALLOWED_ORIGIN")
    ownership = RuntimeOwnership(args.runtime_root.resolve())
    ownership.acquire()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2048)
    port = int(listener.getsockname()[1])

    # Import after the launcher-provided environment is complete. Settings are
    # immutable for the lifetime of this packaged process.
    import uvicorn

    from app.core.desktop_loopback import (
        DesktopLoopbackPolicy,
        DesktopLoopbackSecurityMiddleware,
    )
    from app.public_main import create_app

    runtime_app = create_app()
    policy = DesktopLoopbackPolicy(token, origin)
    runtime_app.add_middleware(DesktopLoopbackSecurityMiddleware, policy=policy)
    config = uvicorn.Config(
        runtime_app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    @runtime_app.post("/__angmoo/desktop/shutdown", include_in_schema=False)
    async def shutdown() -> dict[str, str]:
        server.should_exit = True
        return {"status": "stopping"}

    if not _process_alive(args.parent_pid):
        listener.close()
        ownership.release()
        return 0

    ownership.publish_endpoint(port)
    print(
        json.dumps(
            {
                "event": "ready",
                "host": "127.0.0.1",
                "port": port,
                "pid": os.getpid(),
            }
        ),
        flush=True,
    )
    watcher = threading.Thread(
        target=_watch_parent,
        args=(args.parent_pid, server),
        name="angmoo-parent-watchdog",
        daemon=True,
    )
    watcher.start()
    try:
        server.run(sockets=[listener])
        return 0
    finally:
        listener.close()
        ownership.release()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - process boundary must emit one code
        print(
            json.dumps({"event": "fatal", "code": str(exc)[:120]}),
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from None
