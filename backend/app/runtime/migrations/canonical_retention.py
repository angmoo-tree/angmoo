"""Ownership, use pins and startup-only retention of canonical generations.

No legacy backfill and no implicit destructive permission. Upgrade selection,
pin registration and retention share the embedded migration OS lock.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.runtime.migrations.generation import EmbeddedGenerationController, EmbeddedGenerationError, EmbeddedUpgradeLock

OWNERSHIP_FILE = "generation-retention.json"
POLICY = "canonical-generation-current-previous-v1"
_ALLOWED_FILES = frozenset({OWNERSHIP_FILE, "angmoo.sqlite3", "angmoo.sqlite3-wal", "angmoo.sqlite3-shm"})


class GenerationOwnership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: Literal["canonical-generation-current-previous-v1"] = POLICY
    version: StrictInt = Field(default=1, ge=1, le=1)
    store_kind: Literal["canonical"] = "canonical"
    creation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    relative_path: str
    schema_version: StrictInt = Field(ge=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    validated: StrictBool = False
    promotion_confirmed: StrictBool = False


class GenerationUse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(default=1, ge=1, le=1)
    relative_path: str
    pid: StrictInt = Field(gt=0)
    process_start: str = Field(min_length=1)
    use_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class RemovalIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(default=1, ge=1, le=1)
    ownership: GenerationOwnership


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _read(path: Path, model):
    if _reparse(path):
        raise ValueError("generation_retention_record_reparse")
    if path.stat().st_size > 16384:
        raise ValueError("generation_retention_record_oversized")
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _process_start() -> str:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), ctypes.byref(created),
                ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)):
            raise OSError("generation_process_identity_unavailable")
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    # proc's comm field may contain spaces and closing parentheses.
    payload = Path(f"/proc/{os.getpid()}/stat").read_text(encoding="utf-8")
    return payload[payload.rfind(")") + 2:].split()[19]


def _reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def owned_generation(data_root: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not re.fullmatch(r"generations/[A-Za-z0-9][A-Za-z0-9._-]{0,63}", relative):
        raise ValueError("generation_retention_path_invalid")
    base = data_root.resolve()
    target = base / "canonical" / relative
    for path in (base, base / "canonical", base / "canonical" / "generations", target):
        if path.exists() and _reparse(path):
            raise ValueError("generation_retention_reparse_refused")
    if target.resolve() != target or target.parent != base / "canonical" / "generations":
        raise ValueError("generation_retention_path_not_owned")
    if must_exist and not target.is_dir():
        raise ValueError("generation_retention_directory_missing")
    return target


def record_creation(directory: Path, *, relative: str, schema_version: int, manifest_sha256: str) -> GenerationOwnership:
    # Called only from actual new clean/staging creation, never a selector read.
    record = GenerationOwnership(creation_id=uuid4().hex, relative_path=relative,
        schema_version=schema_version, manifest_sha256=manifest_sha256, created_at=datetime.now(UTC))
    _atomic_json(directory / OWNERSHIP_FILE, record.model_dump(mode="json"))
    return record


def record_validated(directory: Path) -> None:
    path = directory / OWNERSHIP_FILE
    record = _read(path, GenerationOwnership)
    _atomic_json(path, record.model_copy(update={"validated": True}).model_dump(mode="json"))


def confirm_promotion(data_root: Path, *, relative: str, schema_version: int, manifest_sha256: str) -> None:
    path = owned_generation(data_root, relative) / OWNERSHIP_FILE
    if not path.is_file():
        return  # Existing directories and marker recovery do not gain ownership.
    record = _read(path, GenerationOwnership)
    if (record.relative_path != relative or record.schema_version != schema_version
            or record.manifest_sha256 != manifest_sha256 or not record.validated):
        raise ValueError("generation_promotion_confirmation_invalid")
    if not record.promotion_confirmed:
        _atomic_json(path, record.model_copy(update={"promotion_confirmed": True}).model_dump(mode="json"))


class ServingRetentionOwner:
    """Real per-root serving ownership, held until workers/engines have closed."""
    def __init__(self, data_root: Path, *, enabled: bool = True):
        self.data_root = data_root.resolve()
        self.enabled = enabled
        self.pid, self.process_start = os.getpid(), _process_start()
        self._lock = EmbeddedUpgradeLock(self.data_root / "runtime" / "canonical-serving.lock")
        self._held = False

    def acquire(self):
        self._lock.__enter__()
        self._held = True
        return self

    def permits(self, data_root: Path) -> bool:
        return (self.enabled and self._held and self.data_root == data_root.resolve()
            and self.pid == os.getpid() and self.process_start == _process_start())

    def close(self):
        self._lock.__exit__(None, None, None)
        self._held = False


class GenerationUsePin:
    def __init__(self, data_root: Path, relative: str):
        self.data_root, self.relative = data_root.resolve(), relative
        self.record = GenerationUse(relative_path=relative, pid=os.getpid(),
            process_start=_process_start(), use_id=uuid4().hex)
        self.path = self.data_root / "runtime" / "canonical-uses" / (self.record.use_id + ".json")
        self._lock = EmbeddedUpgradeLock(self.path.with_suffix(".lock"))
        self._held = False

    def acquire(self):
        with EmbeddedUpgradeLock(self.data_root / "runtime" / "embedded-data-migration.lock"):
            # Pin a validated future path before the runtime can create/open
            # its DB. This does not tag, migrate or grant deletion ownership.
            owned_generation(self.data_root, self.relative, must_exist=False)
            self._lock.__enter__()
            try:
                _atomic_json(self.path, self.record.model_dump(mode="json"))
                self._held = True
            except BaseException:
                self._lock.__exit__(None, None, None)
                raise
        return self

    def close(self):
        # A completed consumer is safe to unpin only after its actual engine
        # and worker handles close. If upgrade is busy, a stale unlocked pin
        # remains for a later positively confirmed cleanup.
        if not self._held:
            return
        try:
            with EmbeddedUpgradeLock(self.data_root / "runtime" / "embedded-data-migration.lock"):
                self._lock.__exit__(None, None, None)
                self._held = False
                self.path.unlink(missing_ok=True)
                self.path.with_suffix(".lock").unlink(missing_ok=True)
        except (EmbeddedGenerationError, OSError):
            self._lock.__exit__(None, None, None)
            self._held = False


def _protected_uses(data_root: Path) -> set[str]:
    protected = set()
    directory = data_root / "runtime" / "canonical-uses"
    if not directory.exists():
        return protected
    if _reparse(directory):
        raise ValueError("generation_use_directory_ambiguous")
    for path in directory.glob("*.json"):
        if _reparse(path):
            raise ValueError("generation_use_record_ambiguous")
        record = _read(path, GenerationUse)
        owned_generation(data_root, record.relative_path)
        if path.stem != record.use_id:
            raise ValueError("generation_use_record_ambiguous")
        if path.with_suffix(".lock").exists() and _reparse(path.with_suffix(".lock")):
            raise ValueError("generation_use_lock_ambiguous")
        probe = EmbeddedUpgradeLock(path.with_suffix(".lock"))
        try:
            probe.__enter__()
        except EmbeddedGenerationError:
            # The OS lock proves an actual consumer, even if a PID was reused.
            protected.add(record.relative_path)
        else:
            probe.__exit__(None, None, None)
            # Crash recovery: the registered lifetime lock is no longer held.
            path.unlink()
            path.with_suffix(".lock").unlink(missing_ok=True)
    return protected


def _protected_markers(data_root: Path) -> set[str]:
    def read_selection(controller):
        try:
            return controller.current()
        except TypeError as exc:
            # A malformed previous marker must defer retention rather than
            # turn successful selection of the working current into a failure.
            raise ValueError("generation_selection_record_ambiguous") from exc

    def validate(marker):
        from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest, SqliteVersionContractError
        if (not isinstance(marker, dict) or type(marker.get("schema_version")) is not int
                or marker["schema_version"] != 1 or not isinstance(marker.get("relative_path"), str)):
            raise ValueError("generation_selection_record_ambiguous")
        if type(marker.get("data_version")) is not int or marker["data_version"] < 1:
            raise ValueError("generation_marker_version_ambiguous")
        try:
            digest = load_sqlite_manifest(marker["data_version"]).manifest_sha256
        except SqliteVersionContractError as exc:
            raise ValueError("generation_marker_version_ambiguous") from exc
        if digest != marker["manifest_sha256"]:
            raise ValueError("generation_marker_manifest_ambiguous")
        directory = owned_generation(data_root, marker["relative_path"])
        if not (directory / "angmoo.sqlite3").is_file() or _reparse(directory / "angmoo.sqlite3"):
            raise ValueError("generation_marker_database_ambiguous")
    controller = EmbeddedGenerationController(data_root / "canonical", artifact_relative_path="angmoo.sqlite3")
    for path in (controller.current_marker, controller.previous_marker):
        if path.exists() and _reparse(path):
            raise ValueError("generation_selection_record_ambiguous")
    current = read_selection(controller)
    if current is None:
        raise ValueError("generation_current_marker_missing")
    validate(current)
    protected = {current["relative_path"]}
    if controller.previous_marker.exists():
        # Validate previous with the same v1 reader without changing it.
        previous_controller = EmbeddedGenerationController(controller.root, artifact_relative_path="angmoo.sqlite3")
        previous_controller.current_marker = controller.previous_marker
        previous = read_selection(previous_controller)
        if previous is None:
            raise ValueError("generation_previous_selection_ambiguous")
        validate(previous)
        if previous["relative_path"] == current["relative_path"]:
            raise ValueError("generation_previous_selection_ambiguous")
        protected.add(previous["relative_path"])
    return protected | _protected_uses(data_root)


def _inventory(directory: Path) -> None:
    for item in directory.iterdir():
        if item.name not in _ALLOWED_FILES or _reparse(item) or not item.is_file():
            raise ValueError("generation_retention_inventory_ambiguous")


def _verified_ownership(record: GenerationOwnership) -> None:
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest, SqliteVersionContractError
    try:
        digest = load_sqlite_manifest(record.schema_version).manifest_sha256
    except SqliteVersionContractError as exc:
        raise ValueError("generation_ownership_version_ambiguous") from exc
    if (digest != record.manifest_sha256 or not record.validated
            or not record.promotion_confirmed or record.created_at.tzinfo is None):
        raise ValueError("generation_ownership_provenance_ambiguous")


def _remove_generation(data_root: Path, record: GenerationOwnership, intent: Path) -> None:
    # Recheck markers/use references and exact physical paths immediately before
    # every destructive operation. The caller holds the shared upgrade lock.
    _verified_ownership(record)
    if record.relative_path in _protected_markers(data_root):
        raise ValueError("generation_retention_target_protected")
    directory = owned_generation(data_root, record.relative_path, must_exist=False)
    if directory.exists():
        _inventory(directory)
        ownership = directory / OWNERSHIP_FILE
        if ownership.exists() and _read(ownership, GenerationOwnership) != record:
            raise ValueError("generation_retention_ownership_changed")
        # Keep ownership until all DB files have gone, so interrupted removal
        # remains identifiable; the durable outside intent survives even rmdir.
        for name in sorted(_ALLOWED_FILES - {OWNERSHIP_FILE}):
            owned_generation(data_root, record.relative_path)
            (directory / name).unlink(missing_ok=True)
        ownership.unlink(missing_ok=True)
        directory.rmdir()
    intent.unlink(missing_ok=True)


def prune_generations(data_root: Path, *, owner: ServingRetentionOwner | None) -> dict[str, int]:
    """Caller holds upgrade lock and has completed every preservation check."""
    root = data_root.resolve()
    if owner is None or not owner.permits(root):
        return {"unauthorized": 1}
    counts = Counter()
    try:
        protected = _protected_markers(root)
        intents = root / "runtime" / "canonical-removals"
        if intents.exists() and _reparse(intents):
            raise ValueError("generation_removal_directory_ambiguous")
        for intent in sorted(intents.glob("*.json")):
            try:
                record = _read(intent, RemovalIntent).ownership
                if intent.stem != record.creation_id or not record.validated or not record.promotion_confirmed:
                    raise ValueError("generation_removal_intent_invalid")
                _remove_generation(root, record, intent)
                counts["removed"] += 1
            except (OSError, ValueError, EmbeddedGenerationError):
                counts["deferred"] += 1
        generations = root / "canonical" / "generations"
        for directory in sorted(generations.iterdir()):
            relative = "generations/" + directory.name
            if relative in protected:
                counts["protected"] += 1
                continue
            try:
                directory = owned_generation(root, relative)
                path = directory / OWNERSHIP_FILE
                if not path.exists():
                    counts["legacy"] += 1
                    continue
                record = _read(path, GenerationOwnership)
                if record.relative_path != relative or not record.validated or not record.promotion_confirmed:
                    counts["unconfirmed"] += 1
                    continue
                _verified_ownership(record)
                _inventory(directory)
                if relative in _protected_markers(root):
                    counts["protected"] += 1
                    continue
                intent = intents / (record.creation_id + ".json")
                _atomic_json(intent, RemovalIntent(ownership=record).model_dump(mode="json"))
                _remove_generation(root, record, intent)
                counts["removed"] += 1
            except (OSError, ValueError, EmbeddedGenerationError):
                counts["deferred"] += 1
    except (OSError, ValueError, EmbeddedGenerationError):
        counts["protection_ambiguous"] += 1
    return dict(counts)
