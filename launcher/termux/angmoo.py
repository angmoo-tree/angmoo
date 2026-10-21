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
import tempfile
import time
import urllib.request
import uuid

from payload import REPOSITORY, VERSION, proot_archive, read_manifest, require, validate_manifest, validate_candidate_manifest, verify_archive
from processes import alive, atomic_json, await_ready, free_port, identity, session_members, stop_child
from service_logs import Capture, create_session, launcher_hash, open_private, read_session, redact, save_session, select_session, show_logs, utc

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
    "logs_missing": ("No saved log session was found.", "저장된 로그 세션이 없습니다."),
    "service_exited_before_ready": ("A service exited before it was ready. Inspect diagnostics and logs.", "서비스가 준비되기 전에 종료됐습니다. diagnostics와 logs로 확인하세요."),
    "service_readiness_timeout": ("A service did not become ready in time. Inspect diagnostics and logs.", "서비스 준비가 제한 시간 안에 완료되지 않았습니다. diagnostics와 logs로 확인하세요."),
    "logging_degraded": ("Some logs could not be saved. Inspect the reported gaps.", "로그 일부를 저장하지 못했습니다. 기록된 누락 범위를 확인하세요."),
}


def tools() -> str:
    # Native Android Python reports Android separately from Linux.
    require(sys.platform in ("linux", "android"), "host_not_supported")
    try:
        require(importlib.metadata.version("proot-distro") == PROOT_VERSION, "tools_unavailable")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError("tools_unavailable") from exc
    if sys.platform == "android":
        from proot_distro.constants import IS_TERMUX
        require(IS_TERMUX, "host_not_supported")
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
    require(not any(alive(p) or session_members(p) for p in state.get("children", {}).values()), "stale_processes")


def install(home: Path, release: str | None, manifest_path: Path | None, candidate_path: Path | None = None) -> None:
    executable = tools()
    local_candidate = candidate_path is not None
    require(sum(x is not None for x in (release, manifest_path, candidate_path)) == 1, "install_source_invalid")
    manifest_path = candidate_path if local_candidate else manifest_path
    require(platform.machine() in ("aarch64", "arm64") or manifest_path is not None, "host_not_supported")
    with lock(home):
        reject_survivors(home)
        if manifest_path:
            manifest_path = manifest_path.resolve()
            manifest = read_manifest(manifest_path, require_all=False) if local_candidate else read_manifest(manifest_path)
            if local_candidate:
                validate_candidate_manifest(manifest)
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
            with tempfile.TemporaryDirectory(prefix="import-", dir=home) as staging:
                source = f"{item['repository']}@{item['manifest_digest']}"
                if manifest_path:
                    transport = Path(staging) / item["archive"]
                    proot_archive(manifest_path.parent / item["archive"], transport, item)
                    source = str(transport)
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
        atomic_json(home / "installation.json", {"manifest": manifest, "containers": names, "data_root": str(data_root), "proot_version": PROOT_VERSION,
                    "source_kind": "local_candidate" if local_candidate else "release", "host_architecture": platform.machine()})
        print("Installed; run angmoo start. / 설치 완료. angmoo start로 실행하세요.")


def command(executable: str, install: dict, service: str, nonce: str) -> list[str]:
    backend = service == "backend"
    env = {"ANGMOO_LAUNCH_ID": nonce}
    if backend:
        env.update(ANGMOO_BIND_HOST="127.0.0.1", ANGMOO_BACKEND_PORT="8080", ANGMOO_CONTRIBUTOR_DATA_ROOT="/var/lib/angmoo", ANGMOO_FRONTEND_ORIGIN="http://127.0.0.1:3000")
    else:
        env.update(HOSTNAME="127.0.0.1", PORT="3000", ANGMOO_API_BASE_URL="http://127.0.0.1:8080")
    from proot_distro.constants import IS_TERMUX
    result = [executable, "run", install["containers"][service], "--user", "10001:10001" if backend else "1000:1000", "--work-dir", "/app"]
    # This flag exists only on Termux; Linux already omits the Termux host
    # mounts. Use the pinned tool's host detection, not a guessed PREFIX.
    if IS_TERMUX:
        result.append("--isolated")
    if backend:
        result += ["--bind", install["data_root"] + ":/var/lib/angmoo"]
    for key, value in env.items():
        result += ["--env", f"{key}={value}"]
    return result


def installation(home: Path) -> dict:
    path = home / "installation.json"
    require(path.is_file() and not path.is_symlink(), "not_installed")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(value.get("source_kind", "release") in ("release", "local_candidate"), "installation_invalid")
    if value.get("source_kind") == "local_candidate":
        validate_candidate_manifest(value["manifest"])
    else:
        validate_manifest(value["manifest"])
    require(value["proot_version"] == PROOT_VERSION and Path(value["data_root"]) == home / "data", "installation_invalid")
    require(set(value["containers"]) == {"backend", "frontend"} and all(re.fullmatch(r"angmoo-(?:backend|frontend)-[0-9a-f]{12}-[0-9a-f]{12}", v) for v in value["containers"].values()), "installation_invalid")
    return value


def failure_record(exc, service, phase, started, process=None, record=None):
    code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc)) else "service_start_failed"
    summary = code in {"service_start_failed", "service_exited", "service_exited_before_ready", "service_readiness_timeout"}
    return {"service": service, "phase": phase, "observed_at_utc": utc(),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2), "code": code,
            "exception_type": type(exc).__name__, "errno": getattr(exc, "errno", None),
            "message_redacted": redact(str(exc))[:2048], "original_error_observed": not summary,
            "original_error_scope": "host_adapter", "process_identity": record,
            "returncode": process.poll() if process is not None else None, "exit_code_scope": "proot_command",
            "termination_origin": "readiness_timeout" if code == "service_readiness_timeout" else "spontaneous"}


def session_metadata(config):
    return {"launcher_files_sha256": launcher_hash(), "source_sha": config["manifest"]["source_sha"],
            "version": config["manifest"]["version"], "host_architecture": platform.machine(),
            "payload_architecture": "arm64", "images": [{k: i[k] for k in ("service", "manifest_digest")} for i in config["manifest"].get("images", [])],
            "preparation_budget": "image_owned; inspect backend preparation diagnostics"}


def supervise(home: Path, fd: int, nonce: str, *, capture_self=False) -> None:
    # The inheritable flock is held for the entire host session, including drain.
    owner_lock = os.fdopen(fd, "a+")
    children = {}
    state = {"state": "starting", "nonce": nonce, "owner": identity(os.getpid()), "children": {}}
    stopping = False
    started, capture, log_path = time.monotonic(), None, None
    service, phase = "supervisor", "bootstrap"
    state.update(schema="angmoo-host-state.v2", primary_failure=None, cleanup_failures=[], services={})

    def request_stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        config = installation(home)
        log_path = home / "logs" / nonce
        if not log_path.exists():
            log_path = create_session(home, nonce, session_metadata(config))
        capture = Capture(log_path)
        if capture_self:
            # Hand bootstrap stdout/stderr over to the supervisor's bounded
            # collector. Closing the inherited write ends lets start detach.
            class Streams:
                pass
            streams = Streams()
            for name, descriptor in (("stdout", 1), ("stderr", 2)):
                getattr(sys, name).flush()
                reader, writer = os.pipe()
                setattr(streams, name, os.fdopen(reader, "rb", buffering=0))
                os.dup2(writer, descriptor)
                os.close(writer)
            capture.attach("supervisor", streams)
        state["log_reference"] = "logs/" + nonce
        source = config["manifest"]["source_sha"]
        state.update(source_sha=source, version=config["manifest"]["version"])
        atomic_json(home / "state.json", state)
        executable = tools()
        free_port(8080)
        free_port(3000)
        for service, url in (("backend", "http://127.0.0.1:8080/health"), ("frontend", "http://127.0.0.1:3000/api/runtime-identity")):
            require(not stopping, "start_cancelled")
            phase = "spawn"
            process = subprocess.Popen(command(executable, config, service, nonce), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            children[service] = process
            capture.attach(service, process)
            state["children"][service] = identity(process.pid)
            detail = state["services"][service] = {"phase": "readiness", "probe_count": 0, "started_at_utc": utc()}
            phase = "readiness"
            atomic_json(home / "state.json", state)
            def observe(probe):
                detail.update(last_probe=probe, probe_count=detail["probe_count"] + 1)
            await_ready(process, url, source, nonce, backend=service == "backend", cancelled=lambda: stopping or (home / f"stop-{nonce}").exists(), observe=observe)
            detail.update(phase="running", ready_at_utc=utc())
            capture.emit("supervisor", "event", json.dumps({"service": service, "event": "ready", "probe_count": detail["probe_count"]}))
        state["state"] = "running"
        phase = "running"
        atomic_json(home / "state.json", state)
        while not stopping and not (home / f"stop-{nonce}").exists():
            for service, process in children.items():
                require(process.poll() is None, "service_exited")
            time.sleep(0.5)
    except Exception as exc:
        if str(exc) != "start_cancelled":
            state["primary_failure"] = failure_record(exc, service, phase, started, children.get(service), state["children"].get(service))
            state["error"] = state["primary_failure"]["code"]
            if capture:
                capture.emit("supervisor", "error", json.dumps(state["primary_failure"], ensure_ascii=False))
    finally:
        state["state"] = "stopping"
        def persist():
            try:
                atomic_json(home / "state.json", state)
            except OSError as exc:
                if len(state["cleanup_failures"]) < 8:
                    state["cleanup_failures"].append(failure_record(exc, "supervisor", "logging", started))
        persist()
        for service in ("frontend", "backend"):
            if service in children:
                try:
                    record = state["children"].get(service)
                    if record is None:
                        # A child whose identity could not be established must
                        # not authorize signalling an unknown process group.
                        children[service].wait(timeout=1)
                    else:
                        stop_child(children[service], record, 20 if service == "frontend" else 200)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    state["cleanup_failures"].append({"service": service, "phase": "shutdown", "code": "owned_process_stop_failed", "observed_at_utc": utc()})
                primary = state.get("primary_failure") or {}
                detail = state["services"].setdefault(service, {})
                detail.update(returncode=children[service].poll(), exit_code_scope="proot_command", ended_at_utc=utc(),
                              termination_origin=(primary["termination_origin"] if primary.get("service") == service
                                                  else "sibling_failure" if primary else "user_stop"))
                if capture:
                    capture.emit("supervisor", "event", json.dumps({"event": "exit", "service": service, **detail}))
        if capture:
            if capture_self:
                sys.stdout.flush()
                sys.stderr.flush()
                with open(os.devnull, "wb") as null:
                    os.dup2(null.fileno(), 1)
                    os.dup2(null.fileno(), 2)
            coverage = capture.close()
            state["log_capture"] = coverage
            try:
                metadata = read_session(log_path)
                metadata.update(ended_at_utc=utc(), **coverage, primary_failure=state["primary_failure"],
                                cleanup_failures=state["cleanup_failures"], services=state["services"])
                save_session(log_path, metadata)
            except (OSError, ValueError) as exc:
                state["cleanup_failures"].append(failure_record(exc, "supervisor", "logging", started))
        state["state"] = "failed" if state.get("error") or state["cleanup_failures"] else "stopped"
        persist()
        owner_lock.close()


def start(home: Path) -> None:
    tools()
    config = installation(home)
    with lock(home) as owner_lock:
        reject_survivors(home)
        free_port(8080)
        free_port(3000)
        nonce = uuid.uuid4().hex
        path = create_session(home, nonce, session_metadata(config))
        bootstrap = Capture(path, names=("bootstrap",))
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--home", str(home), "_supervise", "--fd", str(owner_lock.fileno()), "--nonce", nonce], pass_fds=(owner_lock.fileno(),), start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            bootstrap.emit("bootstrap", "error", str(exc))
            coverage = bootstrap.close()
            metadata = read_session(path)
            metadata.update(ended_at_utc=utc(), **coverage,
                            primary_failure=failure_record(exc, "supervisor", "spawn", time.monotonic()))
            save_session(path, metadata)
            raise
        bootstrap.attach("bootstrap", process)
        try:
            await_start(home, path, nonce, process)
        except KeyboardInterrupt:
            (home / f"stop-{nonce}").touch(mode=0o600)
            raise ValueError("start_cancelled") from None
        finally:
            coverage = bootstrap.close()
            with open_private(path / "bootstrap-summary.json") as stream:
                stream.write((json.dumps(coverage) + "\n").encode())


def await_start(home, path, nonce, process):
    deadline = time.monotonic() + 370
    while time.monotonic() < deadline:
        state = read_state(home)
        if state.get("nonce") == nonce:
            if state["state"] == "running":
                # The supervisor owns subsequent errors and service pipes.
                print("Angmoo: http://127.0.0.1:3000 / 브라우저에서 이 주소를 여세요.")
                print("Logs: angmoo logs --service all --follow / 로그: angmoo logs --service all --follow")
                return
            if state["state"] in ("stopped", "failed"):
                print(json.dumps(state.get("primary_failure"), ensure_ascii=False), file=sys.stderr)
                raise ValueError(state.get("error", "service_start_failed"))
        if process.poll() is not None:
            state = {"state": "failed", "nonce": nonce, "error": "supervisor_exited", "log_reference": "logs/" + nonce,
                     "primary_failure": {"service": "supervisor", "phase": "bootstrap", "observed_at_utc": utc(),
                                         "returncode": process.returncode, "exit_code_scope": "supervisor", "original_error_observed": False},
                     "log_capture": {"capture_complete": False}}
            atomic_json(home / "state.json", state)
            metadata = read_session(path)
            metadata.update(ended_at_utc=utc(), primary_failure=state["primary_failure"], capture_complete=False)
            save_session(path, metadata)
            raise ValueError("supervisor_exited")
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
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("install")
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--release")
    choice.add_argument("--manifest", type=Path)
    choice.add_argument("--candidate-manifest", type=Path)
    for name in ("start", "stop", "restart", "status"):
        commands.add_parser(name)
    p = commands.add_parser("diagnostics")
    p.add_argument("--session")
    p = commands.add_parser("logs")
    p.add_argument("--session")
    p.add_argument("--service", choices=("backend", "frontend", "supervisor", "all"), default="all")
    p.add_argument("--tail", type=int, choices=range(1, 2001), metavar="1..2000", default=200)
    p.add_argument("--follow", action="store_true")
    p = commands.add_parser("_supervise", help=argparse.SUPPRESS)
    p.add_argument("--fd", type=int, required=True)
    p.add_argument("--nonce", required=True)
    args = parser.parse_args()
    try:
        if args.action == "logs":
            show_logs(args.home, args.service, args.session, args.tail, args.follow)
            return 0
        if args.action in ("status", "diagnostics"):
            state = read_state(args.home.resolve())
            if not alive(state.get("owner", {})) and state.get("state") in ("running", "starting", "stopping"):
                state["state"] = "stale"
            if args.action == "diagnostics":
                path = select_session(args.home, args.session)
                metadata = read_session(path)
                summary = path / "bootstrap-summary.json"
                from service_logs import checked
                bootstrap = json.loads(checked(summary).read_text()) if summary.exists() else None
                print(json.dumps({"current": state, "session": metadata, "bootstrap_capture": bootstrap}, ensure_ascii=False, indent=2))
            else:
                print(json.dumps({k: state[k] for k in ("state", "source_sha", "version", "error", "primary_failure", "log_reference") if k in state}, ensure_ascii=False))
            return 0
        home = private_home(args.home)
        if args.action == "install":
            install(home, args.release, args.manifest, args.candidate_manifest)
        elif args.action == "_supervise":
            require(re.fullmatch(r"[0-9a-f]{32}", args.nonce), "state_invalid")
            supervise(home, args.fd, args.nonce, capture_self=True)
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
