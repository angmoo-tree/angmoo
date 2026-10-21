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
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if len(raw) > 256 * 1024:
        raise ValueError("log_metadata_too_large")
    with open_private(path / "session.tmp") as stream:
        stream.write(raw)
    (path / "session.tmp").replace(path / "session.json")


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


def create_session(home, identifier, metadata):
    if not SESSION_ID.fullmatch(identifier):
        raise ValueError("log_session_invalid")
    root = home / "logs"
    root.mkdir(mode=0o700, exist_ok=True)
    checked(root, directory=True)
    sessions = [p for p in root.iterdir() if SESSION_ID.fullmatch(p.name)]
    removed = []
    # Retention removes only known regular files in completed, owned sessions.
    sizes = {}
    for path in sessions:
        checked(path, directory=True)
        files = list(path.iterdir())
        for file in files:
            checked(file)
        sizes[path] = sum(p.stat().st_size for p in files)
    sessions.sort(key=session_started)
    while sessions and (len(sessions) >= SESSION_LIMIT or sum(sizes.values()) > TOTAL_BYTES - 17 * 1024 * 1024):
        old = sessions[0]
        if not read_session(old).get("ended_at_utc"):
            raise ValueError("log_retention_active_session")
        files = list(old.iterdir())
        allowed = {"session.json", "session.tmp", "bootstrap-summary.json"} | {s + ".jsonl" + suffix for s in SERVICES for suffix in ("", ".1", ".2")}
        if any(p.name not in allowed for p in files):
            raise ValueError("log_retention_unknown_file")
        for file in files:
            checked(file).unlink()
        old.rmdir()
        removed.append(old.name)
        sessions.pop(0)
        sizes.pop(old)
    path = root / identifier
    path.mkdir(mode=0o700)
    value = {"schema": "angmoo-host-logs.v1", "launch_id": identifier,
             "started_at_utc": utc(), "ended_at_utc": None, "capture_complete": False,
             "retention_pruned_sessions": removed, **metadata}
    save_session(path, value)
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
    def __init__(self, path, names=("backend", "frontend", "supervisor"), *, limit=None, queue_bytes=QUEUE_BYTES):
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
        self.writer = threading.Thread(target=self._write, name="angmoo-log-writer", daemon=True)
        self.drainer = threading.Thread(target=self._drain, name="angmoo-log-drain", daemon=True)
        self.writer.start()
        self.drainer.start()

    def attach(self, service, process):
        if service not in self.files:
            raise ValueError("log_service_invalid")
        with self.condition:
            for name in ("stdout", "stderr"):
                stream = getattr(process, name)
                if stream is not None:
                    self.pending.append((service, name, stream))

    def emit(self, service, stream, message, *, partial=False, truncated=False):
        if service not in self.files:
            raise ValueError("log_service_invalid")
        safe = redact(message).encode("utf-8")
        truncated = truncated or len(safe) > MAX_MESSAGE
        safe = safe[:MAX_MESSAGE].decode("utf-8", errors="replace")
        with self.condition:
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
        stop_at = None
        try:
            while True:
                with self.condition:
                    while self.pending:
                        service, name, stream = self.pending.popleft()
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, [service, name, bytearray(), False, False])
                if self.closing.is_set():
                    stop_at = stop_at or time.monotonic() + 2
                    if not selector.get_map():
                        break
                    if time.monotonic() >= stop_at:
                        self.eof_complete = False
                        break
                for key, _ in selector.select(.02):
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
                key.fileobj.close()
            selector.close()
            self.drained.set()
            with self.condition:
                self.condition.notify_all()

    def _write(self):
        flush_at = time.monotonic() + 1
        try:
            while True:
                with self.condition:
                    if not self.queue and not self.drained.is_set():
                        self.condition.wait(.2)
                    item = self.queue.popleft() if self.queue else None
                    if item:
                        self.queued_bytes -= len(item[1])
                    elif self.drained.is_set():
                        break
                if item:
                    try:
                        self.files[item[0]].write(item[1])
                    except (OSError, ValueError) as exc:
                        self.error = type(exc).__name__
                        with self.condition:
                            self._drop(len(item[1]))
                if time.monotonic() >= flush_at:
                    for file in self.files.values():
                        try:
                            file.flush()
                        except (OSError, ValueError) as exc:
                            self.error = type(exc).__name__
                    flush_at = time.monotonic() + 1
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
                "retention_pruned_segments": pruned,
                "capture_complete": self.drained.is_set() and not self.writer.is_alive() and self.eof_complete
                    and not self.dropped_records and not self.truncated_records and not self.error and not pruned}

    def close(self):
        self.closing.set()
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
        print("Log viewing stopped; the service is unchanged. / 로그 보기를 종료했습니다. 서비스는 그대로 실행됩니다.")
    except BrokenPipeError:
        return


def launcher_hash():
    root = Path(__file__).parent
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.glob("*.py")) if not p.name.startswith("test_")}
