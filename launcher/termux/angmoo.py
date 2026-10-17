#!/usr/bin/env python3
"""Angmoo host adapter for Termux / PRoot-Distro 5.10.0.

Install stages immutable ARM64 payloads; only start enters the canonical app
and its existing migration/recovery path. status/diagnostics are read-only.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

from payload import REPOSITORY, VERSION, read_manifest, require, validate_manifest, verify_archive
from processes import alive, atomic_json, await_ready, free_port, identity, stop_child

PROOT_VERSION = "5.10.0"
DEFAULT_HOME = Path.home() / ".local/share/angmoo"
MESSAGES = {
    "tools_unavailable": ("Run the documented one-time setup for PRoot-Distro 5.10.0.", "안내된 최초 준비 명령으로 PRoot-Distro 5.10.0을 준비하세요."),
    "host_not_supported": ("Use Termux on ARM64 or the documented Linux rehearsal.", "ARM64 Termux 또는 안내된 Linux 리허설 환경을 사용하세요."),
    "port_in_use": ("Port 3000 or 8080 is in use. Stop its owner before retrying.", "3000 또는 8080 포트가 사용 중입니다. 해당 프로그램을 종료한 뒤 다시 시도하세요."),
    "already_running": ("Angmoo is already starting or running; use status.", "Angmoo가 시작 중이거나 실행 중입니다. status로 확인하세요."),
    "disk_space_low": ("Free space without deleting Angmoo data, then retry install.", "Angmoo 데이터를 보존하며 여유 공간을 확보한 뒤 설치를 다시 시도하세요."),
    "not_installed": ("Run angmoo install --release 0.1.0 first.", "먼저 angmoo install --release 0.1.0을 실행하세요."),
    "download_failed": ("The official release is unavailable or the connection failed. Existing data is preserved.", "공식 배포물이 없거나 연결에 실패했습니다. 기존 데이터는 보존됩니다."),
    "stale_processes": ("An earlier session still owns processes. Do not start another backend; inspect diagnostics.", "이전 세션의 프로세스가 남아 있습니다. backend를 추가 실행하지 말고 diagnostics로 확인하세요."),
}


def tools() -> str:
    require(sys.platform == "linux", "host_not_supported")
    try:
        require(importlib.metadata.version("proot-distro") == PROOT_VERSION, "tools_unavailable")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError("tools_unavailable") from exc
    executable = shutil.which("proot-distro")
    require(executable and shutil.which("proot"), "tools_unavailable")
    return executable


def private_home(path: Path) -> Path:
    require(not path.is_symlink(), "home_symlink_refused")
    resolved = path.resolve()
    require(not any(str(resolved).startswith(p) for p in ("/sdcard", "/storage", "/mnt/media_rw")), "private_storage_required")
    require(not any(p.is_symlink() for p in (path, *path.parents)), "home_symlink_refused")
    resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(resolved.stat().st_uid == os.getuid() and resolved.stat().st_mode & 0o077 == 0, "home_permissions_invalid")
    return resolved


def lock(home: Path):
    import fcntl
    stream = (home / "host.lock").open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise ValueError("already_running") from exc
    return stream


def read_state(home: Path) -> dict:
    path = home / "state.json"
    if not path.is_file():
        return {"state": "stopped"}
    require(path.stat().st_size < 65536 and not path.is_symlink(), "state_invalid")
    return json.loads(path.read_text(encoding="utf-8"))


def reject_survivors(home: Path):
    state = read_state(home)
    require(not any(alive(p) for p in state.get("children", {}).values()), "stale_processes")


def install(home: Path, release: str | None, manifest_path: Path | None) -> None:
    executable = tools()
    require(platform.machine() in ("aarch64", "arm64") or manifest_path is not None, "host_not_supported")
    with lock(home):
        reject_survivors(home)
        if manifest_path:
            manifest_path = manifest_path.resolve()
            manifest = read_manifest(manifest_path)
        else:
            require(release is not None and VERSION.fullmatch(release), "release_version_invalid")
            url = f"https://github.com/{REPOSITORY}/releases/download/release-v{release}/release-manifest.json"
            try:
                with urllib.request.urlopen(url, timeout=45) as response:
                    data = response.read(4 * 1024 * 1024 + 1)
                require(len(data) <= 4 * 1024 * 1024, "manifest_too_large")
                manifest = json.loads(data)
            except (OSError, ValueError) as exc:
                raise ValueError("download_failed") from exc
            validate_manifest(manifest)
            require(manifest["version"] == release, "manifest_version_mismatch")
        pair = [item for item in manifest["images"] if item["platform"] == "linux/arm64"]
        require(len(pair) == 2, "arm64_pair_missing")
        # Conservative allowance for two extracted filesystems and staging.
        require(shutil.disk_usage(home).free >= max(4 * 1024**3, sum(p["archive_size"] for p in pair) * 4), "disk_space_low")
        for item in pair:
            if manifest_path:
                verify_archive(manifest_path.parent / item["archive"], item)
        names = {}
        nonce = uuid.uuid4().hex[:12]
        for item in pair:
            name = f"angmoo-{item['service']}-{manifest['source_sha'][:12]}-{nonce}"
            source = str(manifest_path.parent / item["archive"]) if manifest_path else f"{item['repository']}@{item['manifest_digest']}"
            subprocess.run([executable, "install", source, "--name", name, "--architecture", "linux/arm64"], check=True)
            # Read the tool's actual installed OCI metadata, never infer an
            # import from a successful command or merely from a directory name.
            from proot_distro.paths import read_container_manifest
            installed = read_container_manifest(name)
            config = installed.get("image_config", {})
            labels = config.get("config", {}).get("Labels", {})
            require(config.get("architecture") == "arm64" and labels.get("org.opencontainers.image.revision") == manifest["source_sha"] and labels.get("org.opencontainers.image.version") == manifest["version"], "installed_payload_mismatch")
            imported_manifest = installed.get("manifest", {})
            require(imported_manifest.get("config", {}).get("digest") == item["config_digest"] and [layer.get("digest") for layer in imported_manifest.get("layers", [])] == item["layers"] and config.get("rootfs", {}).get("diff_ids") == item["diff_ids"], "installed_payload_mismatch")
            names[item["service"]] = name
        data_root = home / "data"
        require(not data_root.is_symlink(), "data_symlink_refused")
        data_root.mkdir(mode=0o700, exist_ok=True)
        require(os.access(data_root, os.W_OK) and data_root.stat().st_mode & 0o077 == 0, "data_permissions_invalid")
        # Selection is atomic only after BOTH imports. Previous roots/data stay.
        atomic_json(home / "installation.json", {"manifest": manifest, "containers": names, "data_root": str(data_root), "proot_version": PROOT_VERSION})
        print("Installed; run angmoo start. / 설치 완료. angmoo start로 실행하세요.")


def command(executable: str, install: dict, service: str, nonce: str) -> list[str]:
    backend = service == "backend"
    env = {"ANGMOO_LAUNCH_ID": nonce}
    if backend:
        env.update(ANGMOO_BIND_HOST="127.0.0.1", ANGMOO_BACKEND_PORT="8080", ANGMOO_CONTRIBUTOR_DATA_ROOT="/var/lib/angmoo", ANGMOO_FRONTEND_ORIGIN="http://127.0.0.1:3000")
    else:
        env.update(HOSTNAME="127.0.0.1", PORT="3000", ANGMOO_API_BASE_URL="http://127.0.0.1:8080")
    result = [executable, "run", install["containers"][service], "--user", "10001:10001" if backend else "1000:1000", "--isolated", "--work-dir", "/app"]
    if backend:
        result += ["--bind", install["data_root"] + ":/var/lib/angmoo"]
    for key, value in env.items():
        result += ["--env", f"{key}={value}"]
    return result


def installation(home: Path) -> dict:
    path = home / "installation.json"
    require(path.is_file() and not path.is_symlink(), "not_installed")
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(value["manifest"])
    require(value["proot_version"] == PROOT_VERSION and Path(value["data_root"]) == home / "data", "installation_invalid")
    require(set(value["containers"]) == {"backend", "frontend"} and all(re.fullmatch(r"angmoo-(?:backend|frontend)-[0-9a-f]{12}-[0-9a-f]{12}", v) for v in value["containers"].values()), "installation_invalid")
    return value


def supervise(home: Path, fd: int, nonce: str) -> None:
    # The inheritable flock is held for the entire host session, including drain.
    owner_lock = os.fdopen(fd, "a+")
    children = {}
    state = {"state": "starting", "nonce": nonce, "owner": identity(os.getpid()), "children": {}}
    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        config = installation(home)
        source = config["manifest"]["source_sha"]
        state.update(source_sha=source, version=config["manifest"]["version"])
        atomic_json(home / "state.json", state)
        executable = tools()
        free_port(8080)
        free_port(3000)
        for service, url in (("backend", "http://127.0.0.1:8080/health"), ("frontend", "http://127.0.0.1:3000/api/runtime-identity")):
            require(not stopping, "start_cancelled")
            process = subprocess.Popen(command(executable, config, service, nonce), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            children[service] = process
            state["children"][service] = identity(process.pid)
            atomic_json(home / "state.json", state)
            await_ready(process, url, source, nonce, backend=service == "backend", cancelled=lambda: stopping or (home / f"stop-{nonce}").exists())
        state["state"] = "running"
        atomic_json(home / "state.json", state)
        while not stopping and not (home / f"stop-{nonce}").exists():
            require(all(p.poll() is None for p in children.values()), "service_exited")
            time.sleep(0.5)
    except Exception as exc:
        state["error"] = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc)) else "service_start_failed"
    finally:
        state["state"] = "stopping"
        atomic_json(home / "state.json", state)
        for service in ("frontend", "backend"):
            if service in children:
                try:
                    stop_child(children[service], state["children"][service], 20 if service == "frontend" else 200)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    state["error"] = "owned_process_stop_failed"
        state["state"] = "failed" if state.get("error") else "stopped"
        atomic_json(home / "state.json", state)
        owner_lock.close()


def start(home: Path) -> None:
    tools()
    installation(home)
    with lock(home) as owner_lock:
        reject_survivors(home)
        free_port(8080)
        free_port(3000)
        nonce = uuid.uuid4().hex
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--home", str(home), "_supervise", "--fd", str(owner_lock.fileno()), "--nonce", nonce], pass_fds=(owner_lock.fileno(),), start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 370
        while time.monotonic() < deadline:
            state = read_state(home)
            if state.get("nonce") == nonce:
                if state["state"] == "running":
                    print("Angmoo: http://127.0.0.1:3000 / 브라우저에서 이 주소를 여세요.")
                    return
                if state["state"] in ("stopped", "failed"):
                    raise ValueError(state.get("error", "service_start_failed"))
            require(process.poll() is None, "supervisor_exited")
            time.sleep(0.5)
        (home / f"stop-{nonce}").touch(mode=0o600)
        raise ValueError("service_readiness_timeout")


def stop(home: Path) -> None:
    state = read_state(home)
    if not alive(state.get("owner", {})):
        reject_survivors(home)
        print("Stopped. / 중지 상태입니다.")
        return
    nonce = state.get("nonce", "")
    require(re.fullmatch(r"[0-9a-f]{32}", nonce), "state_invalid")
    (home / f"stop-{nonce}").touch(mode=0o600)
    deadline = time.monotonic() + 240
    while alive(state["owner"]) and time.monotonic() < deadline:
        time.sleep(0.5)
    require(not alive(state["owner"]), "stop_timeout")
    reject_survivors(home)
    print("Stopped; data preserved. / 종료했습니다. 데이터는 보존됩니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("install")
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--release")
    choice.add_argument("--manifest", type=Path)
    for name in ("start", "stop", "restart", "status", "diagnostics"):
        commands.add_parser(name)
    p = commands.add_parser("_supervise", help=argparse.SUPPRESS)
    p.add_argument("--fd", type=int, required=True)
    p.add_argument("--nonce", required=True)
    args = parser.parse_args()
    try:
        if args.action in ("status", "diagnostics"):
            state = read_state(args.home.resolve())
            if not alive(state.get("owner", {})) and state.get("state") in ("running", "starting", "stopping"):
                state["state"] = "stale"
            print(json.dumps({k: state[k] for k in ("state", "source_sha", "version", "error") if k in state}, ensure_ascii=False))
            return 0
        home = private_home(args.home)
        if args.action == "install":
            install(home, args.release, args.manifest)
        elif args.action == "_supervise":
            require(re.fullmatch(r"[0-9a-f]{32}", args.nonce), "state_invalid")
            supervise(home, args.fd, args.nonce)
        elif args.action == "start":
            start(home)
        elif args.action == "stop":
            stop(home)
        else:
            stop(home)
            start(home)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc)) else "operation_failed"
        en, ko = MESSAGES.get(code, ("Operation could not complete. Existing data is preserved; inspect diagnostics.", "작업을 완료하지 못했습니다. 기존 데이터는 보존됩니다. diagnostics로 확인하세요."))
        print(f"{code}: {en} / {ko}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
