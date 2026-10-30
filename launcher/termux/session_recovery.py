"""One bounded host-only recovery pass under the existing home flock.

Never stops a process, opens a database, or infers death from an HTTP failure.
Legacy sessions without identities are covered by the launch/home/FD scan,
including old PRoot image names and the spawn-before-identity-save window.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import time

from payload import require
from processes import observe_identity, proc_bytes, proc_stat, valid_identity
from service_logs import SESSION_ID, checked, prepared_session, read_session, save_session, utc

MAX_PROCESSES = 4096
MAX_FDS = 16384
MAX_SECONDS = 5.0
MAX_SESSIONS = 32


def _records(value, state):
    records = []
    for key in ("owner_identity", "creator_identity"):
        # The creator hands off once. Its later lifetime is not the runtime's.
        if key == "creator_identity" and (value.get("owner_identity") or value.get("ended_at_utc")
                                           or value.get("lifecycle_state") == "interrupted"):
            continue
        if key in value:
            records.append(value[key])
    children = value.get("children", {})
    require(isinstance(children, dict) and set(children) <= {"backend", "frontend", "postgres"}, "log_recovery_unverified")
    groups = list(children.values())
    if state.get("nonce") == value["launch_id"]:
        if "owner" in state:
            records.append(state["owner"])
        prior = state.get("children", {})
        require(isinstance(prior, dict) and set(prior) <= {"backend", "frontend", "postgres"}, "log_recovery_unverified")
        groups.extend(prior.values())
    records.extend(groups)
    require(all(valid_identity(r) for r in records), "log_recovery_unverified")
    return records, groups


def _metadata(path):
    checked(path, directory=True)
    try:
        value = read_session(path)
    except FileNotFoundError:
        value = prepared_session(path.parent, path)
    require(isinstance(value, dict) and value.get("schema") == "angmoo-host-logs.v1"
            and value.get("launch_id") == path.name and isinstance(value.get("started_at_utc"), str)
            and value.get("lifecycle_state") in (None, "preparing", "running", "closed", "interrupted"), "log_recovery_unverified")
    require(datetime.fromisoformat(value["started_at_utc"]).tzinfo is not None
            and type(value.get("capture_complete")) is bool, "log_recovery_unverified")
    ended, lifecycle = value.get("ended_at_utc"), value.get("lifecycle_state")
    if ended is not None:
        require(isinstance(ended, str) and datetime.fromisoformat(ended).tzinfo is not None
                and lifecycle in (None, "closed"), "log_recovery_unverified")
    if lifecycle == "closed":
        require(ended is not None, "log_recovery_unverified")
    if lifecycle == "interrupted":
        require(value.get("capture_complete") is False and isinstance(value.get("recovery"), dict)
                and value["recovery"].get("basis") == "home_flock_proc_v1", "log_recovery_unverified")
    return value


def _launch_argument(arg, identifiers):
    prefix = b"ANGMOO_LAUNCH_ID="
    return arg.startswith(prefix) and arg[len(prefix):].decode("ascii", errors="replace") in identifiers


def _associated(args, environment, home, identifiers):
    if any(_launch_argument(arg, identifiers) for arg in args + environment):
        return True
    home_bytes = os.fsencode(home)
    if b"_supervise" in args:
        for i, arg in enumerate(args[:-1]):
            if arg == b"--home" and args[i + 1] == home_bytes:
                return True
    # Does not depend on today's installation.json container aliases.
    bind = home_bytes + b"/data:/var/lib/angmoo"
    return any(arg == b"--bind" and args[i + 1] == bind for i, arg in enumerate(args[:-1]))


def scan_processes(home, identifiers, groups, *, proc=Path("/proc")):
    """Scan visible same-UID tasks once; read errors are never absence proof.

    Android hides other apps' proc entries. Their directory UID is sufficient
    to exclude them; an unreadable same-UID process makes this pass unknown.
    The caller owns host.lock, so a supported new session cannot race the scan.
    """
    started = time.monotonic()
    boot = proc_bytes(proc / "sys/kernel/random/boot_id", 128).decode().strip()
    matches, inspected, fd_count = [], 0, 0
    entries = []
    for path in proc.iterdir():
        require(time.monotonic() - started <= MAX_SECONDS, "log_recovery_unverified")
        if path.name.isdigit():
            entries.append(path)
            require(len(entries) <= MAX_PROCESSES, "log_recovery_unverified")
    log_prefix = os.fsencode(home / "logs") + b"/"
    for path in entries:
        try:
            if path.stat().st_uid != os.getuid() or int(path.name) == os.getpid():
                continue
            require(time.monotonic() - started <= MAX_SECONDS, "log_recovery_unverified")
            info, state, sid = proc_stat(path)
            if state == "Z":
                continue
            inspected += 1
            group_match = any(g["boot_id"] == boot and g["pid"] == sid
                              and int(info["start_ticks"]) >= int(g["start_ticks"]) for g in groups)
            args = proc_bytes(path / "cmdline", 256 * 1024).split(b"\0")
            env = proc_bytes(path / "environ", 256 * 1024).split(b"\0")
            matched = group_match or _associated(args, env, home, identifiers)
            # Open log handles also catch legacy capture processes with no
            # launch marker. Do not retain or print command lines/environment.
            for fd in (path / "fd").iterdir():
                fd_count += 1
                require(fd_count <= MAX_FDS and time.monotonic() - started <= MAX_SECONDS, "log_recovery_unverified")
                try:
                    target = os.fsencode(os.readlink(fd))
                except FileNotFoundError:
                    continue  # this particular descriptor closed
                if target.startswith(log_prefix):
                    matched = True
            after, _, _ = proc_stat(path)
            require(after == info, "log_recovery_unverified")
            if matched:
                matches.append({**info, "boot_id": boot})
        except (FileNotFoundError, ProcessLookupError):
            # A disappearing task may have forked after enumeration. Even its
            # UID can be unknown if it exited before stat. Retry a later start,
            # never spin or turn this incomplete snapshot into absence proof.
            raise ValueError("log_recovery_unverified") from None
    return {"matches": matches, "processes_checked": inspected, "fds_checked": fd_count,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}


def recover_sessions(home, state, *, repair=True):
    """Caller must hold the home flock through recovery, retention and handoff."""
    root = home / "logs"
    if not root.exists() and not state.get("nonce"):
        return {"recovered": [], "processes_checked": 0, "fds_checked": 0, "elapsed_ms": 0}
    try:
        if root.exists():
            checked(root, directory=True)
        require(isinstance(state, dict), "log_recovery_unverified")
        paths = []
        for path in root.iterdir() if root.exists() else ():
            if SESSION_ID.fullmatch(path.name):
                paths.append(path)
                require(len(paths) <= MAX_SESSIONS, "log_recovery_unverified")
        values = [(path, _metadata(path)) for path in paths]
        records, groups = [], []
        for _, value in values:
            owned, sessions = _records(value, state)
            records.extend(owned)
            groups.extend(sessions)
        # State may describe a newer launch whose directory was never written.
        if state.get("nonce") and not any(v["launch_id"] == state["nonce"] for _, v in values):
            require(bool(SESSION_ID.fullmatch(state["nonce"])), "log_recovery_unverified")
            owned, sessions = _records({"launch_id": state["nonce"]}, state)
            records.extend(owned)
            groups.extend(sessions)
        identifiers = {v["launch_id"] for _, v in values} | {state.get("nonce", "")}
        before = [observe_identity(r) for r in records]
        require(not any(o["status"] == "unknown" for o in before), "log_recovery_unverified")
        require(not any(o["status"] == "alive" for o in before), "log_recovery_active_session")
        result = scan_processes(home, identifiers, groups)
        # Recheck identities immediately before any metadata mutation. No
        # unbounded retries; uncertain observations preserve every session.
        matches = result.pop("matches")
        observations = [observe_identity(r) for r in records + matches]
        require(not any(o["status"] == "unknown" for o in observations), "log_recovery_unverified")
        require(not any(o["status"] == "alive" for o in observations), "log_recovery_active_session")
        # A related task seen during the scan but gone now may have forked.
        require(not matches, "log_recovery_unverified")
        recovered = []
        for path, value in values:
            if not repair or value.get("ended_at_utc") or value.get("lifecycle_state") == "interrupted":
                continue
            value.update(lifecycle_state="interrupted", capture_complete=False,
                         recovery={"observed_at_utc": utc(), "reason": "owner_and_children_absent",
                                   "basis": "home_flock_proc_v1", **result})
            # Unknown historical end time stays null. Preserve failures/source.
            try:
                save_session(path, value)
            except OSError as exc:
                raise ValueError("log_recovery_write_failed") from exc
            recovered.append(path.name)
        return {"recovered": recovered, **result}
    except ValueError as exc:
        if str(exc) in {"log_recovery_unverified", "log_recovery_active_session", "log_recovery_write_failed"}:
            raise
        raise ValueError("log_recovery_unverified") from exc
    except (OSError, KeyError, IndexError, TypeError, UnicodeError) as exc:
        raise ValueError("log_recovery_unverified") from exc
