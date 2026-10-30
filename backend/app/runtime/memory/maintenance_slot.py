"""Persisted execution ownership, released only after the local work drains."""
import os
import platform
from pathlib import Path
from uuid import uuid4
from datetime import UTC, datetime
from sqlalchemy import select
from app.core.database_transactions import database_write
from app.domains.memory.models.consolidation_request import MemoryMaintenanceSlot as Slot


def process_identity():
    owner = {"host": platform.node(), "pid": os.getpid()}
    try:
        owner["boot"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        owner["start"] = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except OSError:
        pass
    return owner


def proven_inactive(owner):
    current = process_identity()
    if owner.get("host") != current["host"]:
        return False
    if owner.get("boot") and current.get("boot") != owner["boot"]:
        return True
    if os.name == "nt":
        # os.kill(pid, 0) terminates processes on Windows. Query a handle;
        # an inaccessible or reused PID is not proof that this owner stopped.
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(owner["pid"]))
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER
        try:
            status = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(status))) and status.value != 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        if owner.get("start"):
            actual = Path(f"/proc/{int(owner['pid'])}/stat").read_text().rsplit(")", 1)[1].split()[19]
            return actual != owner["start"]
        os.kill(int(owner["pid"]), 0)
    except (FileNotFoundError, ProcessLookupError):
        return True
    except (OSError, ValueError):
        pass
    return False


class MaintenanceSlot:
    def __init__(self, sessions):
        self.sessions = sessions
        self.owner = process_identity()

    def acquire(self, kind, work=None):
        with self.sessions() as db:
            def write():
                dialect = db.get_bind().dialect.name
                if dialect == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert
                else:
                    from sqlalchemy.dialects.sqlite import insert
                db.execute(insert(Slot).values(key="maintenance").on_conflict_do_nothing())
                row = db.scalar(select(Slot).where(Slot.key == "maintenance").with_for_update())
                if row.token and (row.owner is None or not proven_inactive(row.owner)):
                    return None
                token = uuid4().hex
                row.owner, row.token, row.kind = {**self.owner, **({"work": work} if work else {})}, token, kind
                row.acquired_at = datetime.now(UTC)
                return token
            return database_write(db, write, require_clean=True)

    def release(self, token):
        with self.sessions() as db:
            def write():
                row = db.scalar(select(Slot).where(Slot.key == "maintenance").with_for_update())
                if row is not None and row.token == token and row.owner and all(row.owner.get(k) == v for k, v in self.owner.items()):
                    row.last_kind = row.kind
                    row.owner = row.token = row.kind = row.acquired_at = None
            database_write(db, write, require_clean=True)
