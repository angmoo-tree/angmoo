"""Bounded, private host logs. Never opens a product DB or evaluates log text."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import threading
import time
from log_policy import acknowledge

SERVICES = ("backend", "frontend", "supervisor", "bootstrap")
MAX_LINE = 16384
MAX_MESSAGE = 8192
QUEUE_BYTES = 1024 * 1024
SESSION_LIMIT = 4
TOTAL_BYTES = 64 * 1024 * 1024
SESSION_ID = re.compile(r"[0-9a-f]{32}")
SENSITIVE = re.compile(r'''(?i)(?:authorization|(?:set-)?cookie|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token))["']?\s*[:=]''')
TOKENS = re.compile(r"(?i)\bBearer\s+\S+|\bAIza[\w-]{20,}|\bsk-[\w-]{12,}|\beyJ[\w-]+\.[\w-]+\.[\w-]+")


def utc():
    return datetime.now(timezone.utc).isoformat()


def redact(message):
    message = TOKENS.sub("[REDACTED]", message)
    match = SENSITIVE.search(message)
    if match:
        message = message[:match.end()] + " [REDACTED]"
    # Remove terminal control effects, including OSC and CSI escapes.
    message = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "[CONTROL]", message)
    message = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "[CONTROL]", message)
    return "".join(c if c in "\n\t" or ord(c) >= 32 and ord(c) != 127 else "�" for c in message)


def checked(path, *, directory=False):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("log_path_unsafe")
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("log_permissions_invalid")
    if directory and not stat.S_ISDIR(info.st_mode) or not directory and (
            not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise ValueError("log_path_unsafe")
    return path


def open_private(path, *, append=False):
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    flags |= os.O_APPEND if append else os.O_TRUNC
    if path.exists():
        checked(path)
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError("log_path_unsafe")
    return os.fdopen(fd, "wb")


def save_session(path, value):
    save_private_json(path, "session", value)


def save_private_json(path, name, value):
    checked(path, directory=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if len(raw) > 256 * 1024:
        raise ValueError("log_metadata_too_large")
    destination = path / (name + ".json")
    if destination.exists():
        checked(destination)
    with open_private(path / (name + ".tmp")) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    (path / (name + ".tmp")).replace(destination)
    sync_directory(path)


def sync_directory(path):
    # Linux and native Termux support directory fsync. A failure is reported;
    # atomic process-crash recovery is not a promise about damaged storage.
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_session(path):
    file = checked(path / "session.json")
    if file.stat().st_size > 256 * 1024:
        raise ValueError("log_metadata_too_large")
    return json.loads(file.read_text(encoding="utf-8"))


def select_session(home, identifier=None):
    root = home / "logs"
    if not root.exists():
        raise ValueError("logs_missing")
    checked(root, directory=True)
    if identifier is not None:
        if not SESSION_ID.fullmatch(identifier):
            raise ValueError("log_session_invalid")
        return checked(root / identifier, directory=True)
    sessions = [p for p in root.iterdir() if SESSION_ID.fullmatch(p.name)]
    for path in sessions:
        checked(path, directory=True)
    if not sessions:
        raise ValueError("logs_missing")
    return max(sessions, key=session_started)


def session_started(path):
    # Directory mtime also changes on rotation and atomic metadata replacement.
    # Retention order must use the immutable session start, not those writes.
    return datetime.fromisoformat(read_session(path)["started_at_utc"])


def retention_files(path):
    checked(path, directory=True)
    allowed = {"session.json", "session.tmp", "bootstrap-summary.json", "policy-state.json", "policy-state.tmp"} | {
        s + ".jsonl" + suffix for s in SERVICES for suffix in ("", ".1", ".2")}
    files = []
    for file in path.iterdir():
        if file.name not in allowed:
            raise ValueError("log_retention_unknown_file")
        files.append(checked(file))
    return files


def retention_terminal(value):
    if value.get("lifecycle_state") == "interrupted":
        return (value.get("capture_complete") is False
                and isinstance(value.get("recovery"), dict)
                and value.get("recovery", {}).get("basis") == "home_flock_proc_v1")
    return bool(value.get("ended_at_utc")) and value.get("lifecycle_state") in (None, "closed")


def finish_pruning(root, receipt):
    """Resume only our exact, private, prevalidated rename; never a data path."""
    identifier = receipt["target"]
    if not isinstance(identifier, str) or not SESSION_ID.fullmatch(identifier):
        raise ValueError("log_retention_receipt_invalid")
    old, pending = root / identifier, root / (".pruning-" + identifier)
    if old.exists() and pending.exists():
        raise ValueError("log_retention_receipt_invalid")
    if old.exists():
        if receipt["phase"] != "prepared" or not retention_terminal(read_session(old)):
            raise ValueError("log_retention_active_session")
        retention_files(old)
        old.rename(pending)
        sync_directory(root)
    elif not pending.exists() and receipt["phase"] == "prepared":
        raise ValueError("log_retention_receipt_invalid")
    receipt["phase"] = "pruning"
    save_private_json(root, ".retention", receipt)
    if pending.exists():
        files = retention_files(pending)
        if (pending / "session.json").exists():
            value = read_session(pending)
            if value.get("launch_id") != identifier or not retention_terminal(value):
                raise ValueError("log_retention_receipt_invalid")
        # Keep identity metadata until last. The receipt also covers a crash
        # between removing the last file and removing the directory.
        for file in sorted(files, key=lambda p: p.name == "session.json"):
            checked(file).unlink()
        pending.rmdir()
        sync_directory(root)
    if identifier not in receipt["removed"]:
        receipt["removed"].append(identifier)
    receipt.update(phase="complete", target=None)
    save_private_json(root, ".retention", receipt)


def resume_retention(root, identifier):
    receipt = {"schema": "angmoo-log-retention.v1", "phase": "complete", "target": None,
               "removed": [], "for_launch": identifier, "session_created": False}
    file = root / ".retention.json"
    if file.exists():
        checked(file)
        if file.stat().st_size > 256 * 1024:
            raise ValueError("log_retention_receipt_invalid")
        prior = json.loads(file.read_text(encoding="utf-8"))
        if (not isinstance(prior, dict) or prior.get("schema") != receipt["schema"]
                or prior.get("phase") not in ("prepared", "pruning", "complete")
                or not isinstance(prior.get("removed"), list) or len(prior["removed"]) > 32
                or not all(isinstance(i, str) and SESSION_ID.fullmatch(i) for i in prior["removed"])
                or type(prior.get("session_created")) is not bool):
            raise ValueError("log_retention_receipt_invalid")
        if prior["phase"] != "complete":
            finish_pruning(root, prior)
        if not prior["session_created"]:
            receipt["removed"] = prior["removed"]
    # Unknown leftovers must not be adopted. Their files remain untouched.
    if any(p.name.startswith(".pruning-") for p in root.iterdir()):
        raise ValueError("log_retention_receipt_invalid")
    return receipt


def prepared_session(root, path):
    """Recover mkdir-before-metadata interruption using our bounded receipt.

    No log writer can be spawned before create_session returns. Still defer
    every write until the caller has established process absence.
    """
    file = checked(root / ".retention.json")
    if file.stat().st_size > 256 * 1024:
        raise ValueError("log_recovery_unverified")
    receipt = json.loads(file.read_text(encoding="utf-8"))
    if (receipt.get("schema") != "angmoo-log-retention.v1" or receipt.get("phase") != "complete"
            or receipt.get("for_launch") != path.name or receipt.get("session_created") is not False
            or any(p.name != "session.tmp" for p in retention_files(path))):
        raise ValueError("log_recovery_unverified")
    return receipt["pending_session"]


def create_session(home, identifier, metadata):
    try:
        return _create_session(home, identifier, metadata)
    except OSError as exc:
        raise ValueError("log_retention_write_failed") from exc


def _create_session(home, identifier, metadata):
    if not SESSION_ID.fullmatch(identifier):
        raise ValueError("log_session_invalid")
    root = home / "logs"
    root.mkdir(mode=0o700, exist_ok=True)
    checked(root, directory=True)
    receipt = resume_retention(root, identifier)
    sessions = [p for p in root.iterdir() if SESSION_ID.fullmatch(p.name)]
    if len(sessions) > 32:
        raise ValueError("log_retention_limit")
    removed = receipt["removed"]
    # Retention removes only known regular files in completed, owned sessions.
    sizes = {}
    for path in sessions:
        files = retention_files(path)
        sizes[path] = sum(p.stat().st_size for p in files)
    sessions.sort(key=session_started)
    overhead = sum(checked(p).stat().st_size for p in (root / ".retention.json", root / ".retention.tmp") if p.exists())
    while sessions and (len(sessions) >= SESSION_LIMIT or sum(sizes.values()) + overhead > TOTAL_BYTES - 17 * 1024 * 1024):
        old = sessions[0]
        if not retention_terminal(read_session(old)):
            raise ValueError("log_retention_active_session")
        receipt.update(phase="prepared", target=old.name)
        save_private_json(root, ".retention", receipt)
        finish_pruning(root, receipt)
        sessions.pop(0)
        sizes.pop(old)
    value = {"schema": "angmoo-host-logs.v1", "launch_id": identifier,
             "started_at_utc": utc(), "ended_at_utc": None, "capture_complete": False,
             "retention_pruned_sessions": removed, **metadata}
    receipt["pending_session"] = value
    save_private_json(root, ".retention", receipt)
    path = root / identifier
    path.mkdir(mode=0o700)
    save_session(path, value)
    receipt["session_created"] = True
    receipt.pop("pending_session")
    save_private_json(root, ".retention", receipt)
    return path


class RotatingFile:
    def __init__(self, path, limit, segments):
        self.path, self.limit, self.segments = path, limit, segments
        self.stream = open_private(path, append=True)
        self.size = path.stat().st_size
        self.pruned = 0

    def write(self, raw):
        if self.size and self.size + len(raw) > self.limit:
            self.stream.close()
            oldest = self.path.with_name(self.path.name + f".{self.segments - 1}")
            if oldest.exists():
                checked(oldest).unlink()
                self.pruned += 1
            for index in range(self.segments - 2, 0, -1):
                source = self.path.with_name(self.path.name + f".{index}")
                if source.exists():
                    checked(source).replace(self.path.with_name(self.path.name + f".{index + 1}"))
            checked(self.path).replace(self.path.with_name(self.path.name + ".1"))
            self.stream = open_private(self.path)
            self.size = 0
        self.stream.write(raw)
        self.size += len(raw)

    def flush(self):
        self.stream.flush()

    def close(self):
        self.stream.close()


class Capture:
    """One nonblocking pipe drainer and one bounded writer per supervisor."""
    def __init__(self, path, names=("backend", "frontend", "supervisor"), *, limit=None, queue_bytes=QUEUE_BYTES, policy=None):
        checked(path, directory=True)
        self.path, self.started = path, time.monotonic()
        self.files = {}
        try:
            for name in names:
                if name not in SERVICES:
                    raise ValueError("log_service_invalid")
                size, segments = (2 * 1024 * 1024, 3) if name in ("backend", "frontend") else (1024 * 1024, 2)
                self.files[name] = RotatingFile(path / (name + ".jsonl"), limit or size, segments)
        except BaseException:
            for file in self.files.values():
                file.close()
            raise
        self.queue, self.pending = deque(), deque()
        self.condition = threading.Condition()
        self.queued_bytes, self.queue_limit, self.sequence = 0, queue_bytes, 0
        self.dropped_records, self.dropped_bytes, self.truncated_records = 0, 0, 0
        self.first_drop_utc = self.last_drop_utc = None
        self.error = None
        self.closing = threading.Event()
        self.drained = threading.Event()
        self.eof_complete = True
        self.policy, self.policy_ack = policy, {}
        self.wake_read, self.wake_write = os.pipe()
        for fd in (self.wake_read, self.wake_write):
            os.set_blocking(fd, False)
            os.set_inheritable(fd, False)
        self.close_deadline = None
        self.writer = threading.Thread(target=self._write, name="angmoo-log-writer", daemon=True)
        self.drainer = threading.Thread(target=self._drain, name="angmoo-log-drain", daemon=True)
        self.writer.start()
        self.drainer.start()

    def attach(self, service, process):
        if service not in self.files:
            raise ValueError("log_service_invalid")
        with self.condition:
            if self.closing.is_set() or self.drained.is_set():
                raise ValueError("log_capture_closed")
            for name in ("stdout", "stderr"):
                stream = getattr(process, name)
                if stream is not None:
                    self.pending.append((service, name, stream))
            self._wake()

    def _wake(self):
        # Called under the command lock. EAGAIN coalesces with a pending wakeup;
        # the drainer rechecks commands before entering the next blocking select.
        if self.wake_write is not None:
            try:
                os.write(self.wake_write, b"x")
            except BlockingIOError:
                pass

    def emit(self, service, stream, message, *, partial=False, truncated=False):
        if service not in self.files:
            raise ValueError("log_service_invalid")
        safe = redact(message).encode("utf-8")
        truncated = truncated or len(safe) > MAX_MESSAGE
        safe = safe[:MAX_MESSAGE].decode("utf-8", errors="replace")
        with self.condition:
            ack = acknowledge(message, service, self.path.name, self.policy)
            if ack is not None and service not in self.policy_ack:
                self.policy_ack[service] = ack
                self.condition.notify()
            self.sequence += 1
            record = {"received_at_utc": utc(), "elapsed_ms": round((time.monotonic() - self.started) * 1000, 2),
                      "launch_id": self.path.name, "service": service, "stream": stream,
                      "sequence": self.sequence, "message": safe, "partial": partial, "truncated": truncated}
            raw = (json.dumps(record, ensure_ascii=False) + "\n").encode()
            self.truncated_records += int(truncated)
            if self.queued_bytes + len(raw) > self.queue_limit:
                self._drop(len(raw))
                return
            self.queue.append((service, raw))
            self.queued_bytes += len(raw)
            self.condition.notify()

    def _drop(self, size):
        self.dropped_records += 1
        self.dropped_bytes += size
        self.last_drop_utc = utc()
        self.first_drop_utc = self.first_drop_utc or self.last_drop_utc

    def _drain(self):
        selector = selectors.DefaultSelector()
        selector.register(self.wake_read, selectors.EVENT_READ, None)
        try:
            while True:
                with self.condition:
                    while self.pending:
                        service, name, stream = self.pending.popleft()
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, [service, name, bytearray(), False, False])
                if self.closing.is_set():
                    if len(selector.get_map()) == 1:
                        break
                    if time.monotonic() >= self.close_deadline:
                        self.eof_complete = False
                        break
                timeout = max(0, self.close_deadline - time.monotonic()) if self.closing.is_set() else None
                for key, _ in selector.select(timeout):
                    if key.data is None:
                        try:
                            while os.read(key.fd, 4096):
                                pass
                        except BlockingIOError:
                            pass
                        continue
                    service, name, buffer, oversized, sensitive = key.data
                    try:
                        chunk = os.read(key.fd, 16384)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        if buffer and not oversized:
                            text = buffer.decode("utf-8", errors="replace")
                            self.emit(service, name, "[REDACTED continuation]" if sensitive and text[:1].isspace() else text, partial=True)
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    for part in chunk.splitlines(keepends=True):
                        complete = part.endswith(b"\n")
                        if not oversized:
                            buffer.extend(part)
                            if len(buffer) > MAX_LINE:
                                self.emit(service, name, "[oversized line omitted]", partial=not complete, truncated=True)
                                buffer.clear()
                                oversized = True
                        if complete:
                            if not oversized:
                                text = buffer.decode("utf-8", errors="replace").rstrip("\r\n")
                                continuation = sensitive and bool(text[:1].isspace())
                                sensitive = continuation or bool(SENSITIVE.search(text))
                                self.emit(service, name, "[REDACTED continuation]" if continuation else text)
                            buffer.clear()
                            oversized = False
                    key.data[3], key.data[4] = oversized, sensitive
        except (OSError, ValueError) as exc:
            self.error = type(exc).__name__
            self.eof_complete = False
        finally:
            for key in list(selector.get_map().values()):
                if key.data is not None:
                    key.fileobj.close()
            selector.close()
            with self.condition:
                for _, _, stream in self.pending:
                    stream.close()
                self.pending.clear()
                os.close(self.wake_read)
                os.close(self.wake_write)
                self.wake_read = self.wake_write = None
                self.drained.set()
                self.condition.notify_all()

    def _write(self):
        flush_at, dirty, saved_ack_count = None, set(), 0
        try:
            while True:
                with self.condition:
                    while not self.queue and not self.drained.is_set() and len(self.policy_ack) == saved_ack_count:
                        remaining = None if flush_at is None else max(0, flush_at - time.monotonic())
                        if remaining == 0:
                            break
                        self.condition.wait(remaining)
                    acknowledgements = dict(self.policy_ack)
                    item = self.queue.popleft() if self.queue else None
                    if item:
                        self.queued_bytes -= len(item[1])
                    done = not item and self.drained.is_set()
                if len(acknowledgements) != saved_ack_count:
                    try:
                        with open_private(self.path / "policy-state.tmp") as stream:
                            stream.write((json.dumps(acknowledgements) + "\n").encode())
                        (self.path / "policy-state.tmp").replace(self.path / "policy-state.json")
                    except (OSError, ValueError) as exc:
                        self.error = type(exc).__name__
                    saved_ack_count = len(acknowledgements)
                if item:
                    try:
                        self.files[item[0]].write(item[1])
                        dirty.add(item[0])
                        if flush_at is None:
                            flush_at = time.monotonic() + 1
                    except (OSError, ValueError) as exc:
                        self.error = type(exc).__name__
                        with self.condition:
                            self._drop(len(item[1]))
                if flush_at is not None and (done or time.monotonic() >= flush_at):
                    for name in dirty:
                        try:
                            self.files[name].flush()
                        except (OSError, ValueError) as exc:
                            self.error = type(exc).__name__
                    dirty.clear()
                    flush_at = None
                if done:
                    break
        finally:
            for file in self.files.values():
                try:
                    file.close()
                except (OSError, ValueError) as exc:
                    self.error = type(exc).__name__

    def snapshot(self):
        pruned = sum(f.pruned for f in self.files.values())
        return {"dropped_records": self.dropped_records, "dropped_bytes": self.dropped_bytes,
                "first_drop_utc": self.first_drop_utc, "last_drop_utc": self.last_drop_utc,
                "truncated_records": self.truncated_records, "logging_error": self.error,
                "source_policy_acknowledgements": dict(self.policy_ack),
                "retention_pruned_segments": pruned,
                "capture_complete": self.drained.is_set() and not self.writer.is_alive() and self.eof_complete
                    and not self.dropped_records and not self.truncated_records and not self.error and not pruned}

    def close(self):
        with self.condition:
            if not self.closing.is_set():
                self.close_deadline = time.monotonic() + 2
                self.closing.set()
                self._wake()
        self.drainer.join(3)
        self.writer.join(3)
        return self.snapshot()


def tail(path, service="all", count=200):
    if service not in (*SERVICES, "all") or not 1 <= count <= 2000:
        raise ValueError("log_options_invalid")
    names = SERVICES if service == "all" else ("supervisor", "bootstrap") if service == "supervisor" else (service,)
    records = []
    for name in names:
        lines = deque(maxlen=count)
        for suffix in (".2", ".1", ""):
            file = path / (name + ".jsonl" + suffix)
            if not file.exists():
                continue
            checked(file)
            with file.open("rb") as stream:
                while raw := stream.readline(64 * 1024):
                    if not raw.endswith(b"\n"):
                        continue
                    try:
                        record = json.loads(raw)
                    except (UnicodeDecodeError, ValueError):
                        continue  # A writer or abrupt exit can leave a partial tail.
                    if record.get("service") == name and record.get("launch_id") == path.name:
                        lines.append(record)
        records.extend(lines)
    records.sort(key=lambda r: (r["received_at_utc"], r["service"], r["sequence"]))
    output, size = deque(), 0
    for record in reversed(records[-count:]):
        size += len(json.dumps(record).encode())
        if size > 1024 * 1024:
            break
        output.appendleft(record)
    return list(output)


def show_logs(home, service, identifier, count, follow):
    path = select_session(home, identifier)
    seen = {name: 0 for name in SERVICES}
    try:
        while True:
            for record in tail(path, service, count):
                name, sequence = record["service"], record["sequence"]
                if sequence <= seen[name]:
                    continue
                seen[name] = sequence
                print(f"{record['received_at_utc']} {name}/{record['stream']} {redact(record['message'])}", flush=True)
            if not follow:
                return
            time.sleep(.5)
    except KeyboardInterrupt:
        print("Log viewing stopped; the service is unchanged.")
    except BrokenPipeError:
        return


def launcher_hash():
    root = Path(__file__).parent
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.glob("*.py")) if not p.name.startswith("test_")}
