from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
import ladybug as lb
import uvicorn

from ladybug_probe import ExclusiveWriterLock
from windows_path_alias import WindowsAsciiPathAlias


def _parent_is_alive(parent_pid: int) -> bool:
    if parent_pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(parent_pid, 0)
            return True
        except OSError:
            return False
    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, parent_pid)
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) != wait_object_0
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class Runtime:
    def __init__(self, auth_token: str, parent_pid: int, lock_path: Path, graph_path: Path) -> None:
        self.auth_token = auth_token
        self.parent_pid = parent_pid
        self.lock = ExclusiveWriterLock(lock_path)
        self.lock.acquire()
        self.path_alias = WindowsAsciiPathAlias(graph_path.resolve().parent)
        try:
            graph_path = graph_path.resolve()
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            native_root = self.path_alias.__enter__()
            self.database = lb.Database(str(native_root / graph_path.name))
            self.connection = lb.Connection(self.database)
            self.connection.execute("CREATE NODE TABLE IF NOT EXISTS Probe(id STRING PRIMARY KEY, value STRING)")
            self.connection.execute(
                "MERGE (p:Probe {id: $id}) SET p.value = $value RETURN p.id",
                parameters={"id": "packaged-native", "value": "ladybug-ok"},
            )
        except Exception:
            self.path_alias.close()
            self.lock.release()
            raise

    def graph_proof(self) -> dict[str, Any]:
        result = self.connection.execute(
            "MATCH (p:Probe {id: $id}) RETURN p.id, p.value",
            parameters={"id": "packaged-native"},
        )
        row = list(result.get_next()) if result.has_next() else []
        return {"row": row, "embedded_graph": row == ["packaged-native", "ladybug-ok"]}

    def close(self) -> None:
        try:
            self.connection = None
            self.database = None
            gc.collect()
            self.path_alias.close()
        finally:
            self.lock.release()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-token", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--lock-file", required=True, type=Path)
    parser.add_argument("--graph-path", required=True, type=Path)
    args = parser.parse_args()
    if len(args.auth_token) < 24:
        print(json.dumps({"event": "fatal", "error_class": "invalid_auth_token"}), flush=True)
        return 2

    try:
        runtime = Runtime(args.auth_token, args.parent_pid, args.lock_file, args.graph_path)
    except RuntimeError as exc:
        print(json.dumps({"event": "fatal", "error_class": str(exc)}), flush=True)
        return 17

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    server_holder: dict[str, uvicorn.Server] = {}

    def require_token(x_angmoo_spike_token: str | None = Header(default=None)) -> None:
        import hmac

        supplied = x_angmoo_spike_token or ""
        if not hmac.compare_digest(supplied, runtime.auth_token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health", dependencies=[Depends(require_token)])
    async def health() -> dict[str, Any]:
        return {"status": "ok", "parent_alive": _parent_is_alive(runtime.parent_pid)}

    @app.get("/graph-proof", dependencies=[Depends(require_token)])
    async def graph_proof() -> dict[str, Any]:
        return runtime.graph_proof()

    @app.post("/shutdown", dependencies=[Depends(require_token)])
    async def shutdown() -> dict[str, str]:
        server_holder["server"].should_exit = True
        return {"status": "draining"}

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server_holder["server"] = server
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = int(listener.getsockname()[1])

    def watchdog() -> None:
        while not server.should_exit:
            if not _parent_is_alive(runtime.parent_pid):
                server.should_exit = True
                break
            time.sleep(0.25)

    thread = threading.Thread(target=watchdog, name="parent-watchdog", daemon=True)
    thread.start()
    print(json.dumps({"event": "ready", "host": "127.0.0.1", "port": port}), flush=True)
    try:
        asyncio.run(server.serve(sockets=[listener]))
    finally:
        runtime.close()
        listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
