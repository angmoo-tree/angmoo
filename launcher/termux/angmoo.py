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
from log_policy import ENVIRONMENT, PolicyClock, describe, duration, new_policy
from session_recovery import recover_sessions

PROOT_VERSION = "5.10.0"
BACKEND_READINESS_SECONDS = 180.0
FRONTEND_READINESS_SECONDS = 180.0
START_READINESS_SECONDS = 370.0
DEFAULT_HOME = Path.home() / ".local/share/angmoo"
MESSAGES = {
    "log_options_invalid": "Use basic without a duration, or detailed with an integer duration of 1m..60m.",
    "tools_unavailable": "Run the documented one-time setup for PRoot-Distro 5.10.0.",
    "host_not_supported": "Use Termux on ARM64 or the documented Linux rehearsal.",
    "port_in_use": "Port 3000 or 8080 is in use. Stop its owner before retrying.",
    "already_running": "Angmoo is already starting or running; use status.",
    "disk_space_low": "Free space without deleting Angmoo data, then retry install.",
    "not_installed": "Run angmoo install --release 0.1.2 first.",
    "download_failed": "The official release is unavailable or the connection failed. Existing data is preserved.",
    "stale_processes": "An earlier session still owns processes. Do not start another backend; inspect diagnostics.",
    "logs_missing": "No saved log session was found.",
    "service_exited_before_ready": "A service exited before it was ready. Inspect diagnostics and logs.",
    "service_readiness_timeout": "A service did not become ready in time. Inspect diagnostics and logs.",
    "logging_degraded": "Some logs could not be saved. Inspect the reported gaps.",
    "log_recovery_active_session": "An earlier Angmoo session still has running processes. A second server was not started.",
    "log_recovery_unverified": "Could not verify whether an earlier session has ended. A second server was not started; inspect diagnostics.",
    "log_recovery_write_failed": "Interrupted session metadata could not be saved. No new server was started; inspect diagnostics before retrying.",
    "log_retention_write_failed": "Log retention could not finish. No new server was started; the next start will recheck the saved cleanup record.",
    "log_retention_receipt_invalid": "Log cleanup could not be verified. Existing data is preserved; inspect diagnostics.",
}


def is_termux_host() -> bool:
    # The pinned tool initializes its own umask at import. Keep the adapter's
    # private-file policy; importing a dependency must not broaden new files.
    previous = os.umask(0o077)
    try:
        from proot_distro.constants import IS_TERMUX
        return IS_TERMUX
    finally:
        os.umask(previous)


def tools() -> str:
    # Native Android Python reports Android separately from Linux.
    require(sys.platform in ("linux", "android"), "host_not_supported")
    try:
        require(importlib.metadata.version("proot-distro") == PROOT_VERSION, "tools_unavailable")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError("tools_unavailable") from exc
    termux = is_termux_host()
    require(sys.platform != "android" or termux, "host_not_supported")
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
    stream = open_private(home / "host.lock", append=True)
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
        recover_sessions(home, read_state(home), repair=False)
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
        print("Installed; run angmoo start.")


def command(executable: str, install: dict, service: str, nonce: str, *, log_policy=None) -> list[str]:
    backend = service == "backend"
    env = {"ANGMOO_LAUNCH_ID": nonce}
    if log_policy is not None:
        env[ENVIRONMENT] = log_policy
    if backend:
        env.update(ANGMOO_BIND_HOST="127.0.0.1", ANGMOO_BACKEND_PORT="8080", ANGMOO_CONTRIBUTOR_DATA_ROOT="/var/lib/angmoo", ANGMOO_FRONTEND_ORIGIN="http://127.0.0.1:3000")
    else:
        env.update(HOSTNAME="127.0.0.1", PORT="3000", ANGMOO_API_BASE_URL="http://127.0.0.1:8080")
    result = [executable, "run", install["containers"][service], "--user", "10001:10001" if backend else "1000:1000", "--work-dir", "/app"]
    # This flag exists only on Termux; Linux already omits the Termux host
    # mounts. Use the pinned tool's host detection, not a guessed PREFIX.
    if is_termux_host():
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
            "preparation_budget": "image_owned; inspect backend preparation diagnostics",
            "service_readiness_seconds": {"backend": BACKEND_READINESS_SECONDS, "frontend": FRONTEND_READINESS_SECONDS,
                                          "start": START_READINESS_SECONDS}}


def supervise(home: Path, fd: int, nonce: str, *, capture_self=False) -> None:
    # The inheritable flock is held for the entire host session, including drain.
    owner_lock = os.fdopen(fd, "ab")
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
            recover_sessions(home, read_state(home))
            log_path = create_session(home, nonce, {**session_metadata(config), "log_policy": new_policy(nonce, "basic", 0),
                                                  "lifecycle_state": "preparing", "creator_identity": state["owner"]})
        metadata = read_session(log_path)
        # Once spawned, only the supervisor writes session.json until it exits.
        # start writes bootstrap-summary.json, not the supervisor's metadata.
        metadata.update(owner_identity=state["owner"], children={})
        save_session(log_path, metadata)
        policy = metadata.get("log_policy") or new_policy(nonce, "basic", 0)
        policy_clock = PolicyClock(policy)
        state["log_policy"] = policy
        capture = Capture(log_path, policy=policy)
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
            process = subprocess.Popen(command(executable, config, service, nonce, log_policy=policy_clock.envelope(service)), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            children[service] = process
            capture.attach(service, process)
            state["children"][service] = identity(process.pid)
            metadata["children"] = dict(state["children"])
            save_session(log_path, metadata)
            detail = state["services"][service] = {"phase": "readiness", "probe_count": 0, "started_at_utc": utc()}
            phase = "readiness"
            atomic_json(home / "state.json", state)
            def observe(probe):
                detail.update(last_probe=probe, probe_count=detail["probe_count"] + 1)
            await_ready(process, url, source, nonce, expected_version=config["manifest"]["version"], backend=service == "backend",
                        timeout=BACKEND_READINESS_SECONDS if service == "backend" else FRONTEND_READINESS_SECONDS,
                        cancelled=lambda: stopping or (home / f"stop-{nonce}").exists(), observe=observe)
            detail.update(phase="running", ready_at_utc=utc())
            capture.emit("supervisor", "event", json.dumps({"service": service, "event": "ready", "probe_count": detail["probe_count"]}))
        state["state"] = "running"
        metadata["lifecycle_state"] = "running"
        save_session(log_path, metadata)
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
                cleanup_complete = not any(f.get("phase") == "shutdown" for f in state["cleanup_failures"])
                metadata.update(ended_at_utc=utc() if cleanup_complete else None,
                                lifecycle_state="closed" if cleanup_complete else "running",
                                **coverage, primary_failure=state["primary_failure"],
                                cleanup_failures=state["cleanup_failures"], services=state["services"])
                if not cleanup_complete:
                    metadata["capture_complete"] = False
                save_session(log_path, metadata)
            except (OSError, ValueError) as exc:
                state["cleanup_failures"].append(failure_record(exc, "supervisor", "logging", started))
        state["state"] = "failed" if state.get("error") or state["cleanup_failures"] else "stopped"
        persist()
        owner_lock.close()


def start(home: Path, *, log_mode="basic", log_duration=None) -> None:
    seconds = duration(log_mode, log_duration)
    tools()
    with lock(home) as owner_lock:
        config = installation(home)
        recovered = recover_sessions(home, read_state(home))
        if recovered["recovered"]:
            print("Recovered interrupted log sessions. Their logs may be incomplete.")
        reject_survivors(home)
        free_port(8080)
        free_port(3000)
        nonce = uuid.uuid4().hex
        policy = new_policy(nonce, log_mode, seconds)
        path = create_session(home, nonce, {**session_metadata(config), "log_policy": policy,
                                          "lifecycle_state": "preparing", "creator_identity": identity(os.getpid())})
        bootstrap = Capture(path, names=("bootstrap",))
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--home", str(home), "_supervise", "--fd", str(owner_lock.fileno()), "--nonce", nonce], pass_fds=(owner_lock.fileno(),), start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            bootstrap.emit("bootstrap", "error", str(exc))
            coverage = bootstrap.close()
            metadata = read_session(path)
            metadata.update(ended_at_utc=utc(), lifecycle_state="closed", **coverage,
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
    deadline = time.monotonic() + START_READINESS_SECONDS
    while time.monotonic() < deadline:
        state = read_state(home)
        if state.get("nonce") == nonce:
            if state["state"] == "running":
                # The supervisor owns subsequent errors and service pipes.
                print("Angmoo: http://127.0.0.1:3000")
                print("Logs: angmoo logs --service all --follow")
                return
            if state["state"] in ("stopped", "failed"):
                print(json.dumps(state.get("primary_failure"), ensure_ascii=False), file=sys.stderr)
                raise ValueError(state.get("error", "service_start_failed"))
        if process.poll() is not None:
            state = {**(state if state.get("nonce") == nonce else {}),
                     "state": "failed", "nonce": nonce, "error": "supervisor_exited", "log_reference": "logs/" + nonce,
                     "primary_failure": {"service": "supervisor", "phase": "bootstrap", "observed_at_utc": utc(),
                                         "returncode": process.returncode, "exit_code_scope": "supervisor", "original_error_observed": False},
                     "log_capture": {"capture_complete": False}}
            atomic_json(home / "state.json", state)
            metadata = read_session(path)
            # Supervisor death does not establish child death. Leave the
            # session unfinished for the locked recovery pass on next start.
            metadata.update(primary_failure=state["primary_failure"], capture_complete=False)
            save_session(path, metadata)
            raise ValueError("supervisor_exited")
        time.sleep(0.5)
    (home / f"stop-{nonce}").touch(mode=0o600)
    raise ValueError("service_readiness_timeout")


def stop(home: Path) -> None:
    state = read_state(home)
    if not alive(state.get("owner", {})):
        reject_survivors(home)
        print("Stopped.")
        return
    nonce = state.get("nonce", "")
    require(re.fullmatch(r"[0-9a-f]{32}", nonce), "state_invalid")
    (home / f"stop-{nonce}").touch(mode=0o600)
    deadline = time.monotonic() + 240
    while alive(state["owner"]) and time.monotonic() < deadline:
        time.sleep(0.5)
    require(not alive(state["owner"]), "stop_timeout")
    reject_survivors(home)
    print("Stopped; data preserved.")


def policy_status(path, policy):
    from service_logs import checked
    source = path / "policy-state.json"
    acknowledgements = {}
    if source.exists():
        checked(source)
        require(source.stat().st_size <= 8192, "log_metadata_too_large")
        acknowledgements = json.loads(source.read_text(encoding="utf-8"))
    return describe(policy, acknowledgements)


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
        p = commands.add_parser(name)
        if name in ("start", "restart"):
            p.add_argument("--log-mode", choices=("basic", "detailed"), default="basic", help="Service log detail for this launch only (default: basic).")
            p.add_argument("--log-duration", help="Detailed mode duration: 1m..60m (default: 15m, includes startup).")
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
        if args.action in ("start", "restart"):
            duration(args.log_mode, args.log_duration)  # Validate before stop or any filesystem mutation.
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
                print(json.dumps({"current": state, "session": metadata, "bootstrap_capture": bootstrap,
                                  "log_policy": policy_status(path, metadata.get("log_policy"))}, ensure_ascii=False, indent=2))
            else:
                result = {k: state[k] for k in ("state", "source_sha", "version", "error", "primary_failure", "log_reference", "log_capture") if k in state}
                result["log_policy"] = policy_status(select_session(args.home, state["nonce"]), state.get("log_policy")) if state.get("log_reference") else describe(None)
                print(json.dumps(result, ensure_ascii=False))
            return 0
        home = private_home(args.home)
        if args.action == "install":
            install(home, args.release, args.manifest, args.candidate_manifest)
        elif args.action == "_supervise":
            require(re.fullmatch(r"[0-9a-f]{32}", args.nonce), "state_invalid")
            supervise(home, args.fd, args.nonce, capture_self=True)
        elif args.action == "start":
            start(home, log_mode=args.log_mode, log_duration=args.log_duration)
        elif args.action == "stop":
            stop(home)
        else:
            stop(home)
            start(home, log_mode=args.log_mode, log_duration=args.log_duration)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc)) else "operation_failed"
        message = MESSAGES.get(code, "Operation could not complete. Existing data is preserved; inspect diagnostics.")
        print(f"{code}: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
