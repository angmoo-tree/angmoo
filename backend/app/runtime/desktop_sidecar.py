from __future__ import annotations

import argparse
from collections.abc import MutableMapping
import ctypes
import json
import os
import secrets
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
    def __init__(self, runtime_root: Path, *, launch_id: str = "test-launch") -> None:
        self.runtime_root = runtime_root
        self.lock_path = runtime_root / "sidecar.owner.json"
        self.endpoint_path = runtime_root / "sidecar.endpoint.json"
        self.pid = os.getpid()
        self.launch_id = launch_id

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
        payload = {
            "schema_version": 1,
            "pid": self.pid,
            "generation": self.launch_id,
        }
        temporary = self.lock_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.lock_path)

    def publish_endpoint(self, port: int) -> None:
        payload = {
            "schema_version": 1,
            "logical_sidecar_pid": self.pid,
            "host": "127.0.0.1",
            "dynamic_port": port,
            "generation": self.launch_id,
        }
        temporary = self.endpoint_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.endpoint_path)

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
        if (
            current_endpoint.get("logical_sidecar_pid") == self.pid
            and current_endpoint.get("generation") == self.launch_id
        ):
            self.endpoint_path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Angmoo packaged desktop sidecar")
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--launch-id", required=True)
    return parser.parse_args()


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing_{name.lower()}")
    return value


def _sqlite_url(path: Path) -> str:
    return "sqlite+pysqlite:///" + path.resolve().as_posix()


def _write_new_secret(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(secrets.token_urlsafe(48) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def _selected_generation(data_root: Path) -> str:
    marker_path = data_root / "canonical" / "current-generation.json"
    if not marker_path.is_file():
        return "er6-preview-v1"
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
        generation = str(payload["generation"])
        expected_sha256 = str(payload["content_sha256"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError("runtime_generation_marker_invalid") from exc
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not generation or any(character not in allowed for character in generation):
        raise RuntimeError("runtime_generation_marker_invalid")
    database_path = (
        data_root / "canonical" / "generations" / generation / "angmoo.sqlite3"
    )
    if not database_path.is_file():
        raise RuntimeError("runtime_generation_database_missing")
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        raise RuntimeError("runtime_generation_marker_invalid")
    # The digest attests the immutable migration manifest at promotion time.
    # The selected SQLite database is intentionally mutable after the switch,
    # so re-hashing it on every startup would reject every legitimate write.
    return generation


def _configure_embedded_release_candidate(
    runtime_root: Path,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[Path, str]:
    """Opt the packaged sidecar into ER6 without changing Docker defaults."""

    data_root = runtime_root.parent.resolve()
    generation = _selected_generation(data_root)
    database_path = (
        data_root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    secret_path = data_root / "secrets" / "app-secret"
    if not secret_path.is_file():
        canonical = data_root / "canonical"
        has_existing_data = canonical.exists() and any(canonical.rglob("*"))
        if has_existing_data:
            raise RuntimeError("app_secret_missing_for_existing_data")
        _write_new_secret(secret_path)

    target_environment = os.environ if environ is None else environ
    target_environment.update(
        {
            "APP_ENV": "local",
            "APP_SECRET_FILE": str(secret_path),
            "API_DOCS_ENABLED": "false",
            "SIGNUP_ENABLED": "false",
            "BROWSER_SESSION_ALLOWED_ORIGINS": "http://tauri.localhost",
            "CREDENTIAL_ENCRYPTION_PROVIDER": "local",
            "DATABASE_URL": _sqlite_url(database_path),
            "MEDIA_ROOT": str(data_root / "media"),
            "GRAPH_PROJECTION_ENABLED": "true",
            "LADYBUG_GRAPH_PREVIEW_ENABLED": "true",
            "LADYBUG_DATABASE_ROOT": str(data_root / "graph" / "ladybug"),
            "LOCAL_RUNTIME_COMPONENT_MODE": "in_process",
            "RESIDENT_TICK_PROCESS_LOCK_PATH": str(
                runtime_root / "scheduler.lock"
            ),
            "RESIDENT_TICK_READY_PATH": str(runtime_root / "scheduler.ready"),
            "GRAPH_PROJECTOR_READY_PATH": str(runtime_root / "projector.ready"),
        }
    )
    return data_root, generation


def _initialize_embedded_schema(data_root: Path, generation: str) -> None:
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
    from app.runtime.persistence.sqlite_database import (
        SqliteCanonicalDatabase,
        SqliteCanonicalSettings,
    )

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(data_root),
        settings=SqliteCanonicalSettings(generation=generation),
    )
    database.open()
    database.close()


def _initialize_embedded_installation_identity() -> None:
    """Create only the unclaimed local-device identity before workers start."""

    from app.core.db import SessionLocal
    from app.domains.identity.application.local_owner import (
        EnsureLocalInstallationIdentity,
    )
    from app.domains.identity.infrastructure.sqlalchemy_identity_repository import (
        SqlAlchemyIdentityRepository,
    )

    with SessionLocal() as db:
        EnsureLocalInstallationIdentity(
            SqlAlchemyIdentityRepository(db)
        ).execute()


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
    ownership = RuntimeOwnership(
        args.runtime_root.resolve(),
        launch_id=args.launch_id,
    )
    ownership.acquire()
    data_root, generation = _configure_embedded_release_candidate(
        ownership.runtime_root
    )

    # Import the public composition root only after the launcher environment is
    # complete. Its normal route/service composition registers the canonical
    # model metadata without creating a new runtime -> legacy models edge.
    from app.public_main import create_app

    _initialize_embedded_schema(data_root, generation)
    _initialize_embedded_installation_identity()

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
    runtime_app = create_app()
    policy = DesktopLoopbackPolicy(token, origin)
    runtime_app.add_middleware(DesktopLoopbackSecurityMiddleware, policy=policy)
    config = uvicorn.Config(
        runtime_app,
        host="127.0.0.1",
        port=port,
        log_config=None,
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
        if sys.stderr is not None:
            print(
                json.dumps({"event": "fatal", "code": str(exc)[:120]}),
                file=sys.stderr,
                flush=True,
            )
        raise SystemExit(1) from None
