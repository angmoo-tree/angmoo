"""Process-owned, expiring World Package download artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import secrets
import shutil
import threading

from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.export import EXPORT_TOKEN_TTL_SECONDS


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    operation_id: str
    owner_id: str
    token_digest: str
    path: Path
    filename: str
    expires_at: datetime
    package_id: str
    package_version: int
    source_world_id: str
    seed_digest: str
    manifest_digest: str
    license_expression: str
    request_digest: str
    idempotency_key_digest: str
    download_token: str = field(repr=False)


class FilesystemWorldPackageExportArtifacts:
    def __init__(self, root: Path) -> None:
        self._root = (root / "world-packages" / "exports").resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, ExportArtifact] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()
        self.cleanup_expired()

    def create(
        self,
        *,
        operation_id: str,
        owner_id: str,
        filename: str,
        content: bytes,
        package_id: str,
        package_version: int,
        source_world_id: str,
        seed_digest: str,
        manifest_digest: str,
        license_expression: str,
        request_digest: str,
        idempotency_key: str,
    ) -> tuple[ExportArtifact, str, bool]:
        self.cleanup_expired()
        idempotency_digest = hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()
        idempotency_identity = (owner_id, idempotency_digest)
        with self._lock:
            prior_id = self._idempotency.get(idempotency_identity)
            prior = self._items.get(prior_id) if prior_id is not None else None
            if prior is not None and prior.expires_at > datetime.now(timezone.utc):
                if prior.request_digest != request_digest:
                    raise WorldPackageContractError(
                        WorldPackageReasonCode.COMMIT_CONFLICT
                    )
                return prior, prior.download_token, True
            if prior_id is not None:
                expired_artifact = self._discard_locked(prior_id)
                if expired_artifact is not None:
                    shutil.rmtree(
                        expired_artifact.path.parent, ignore_errors=True
                    )

            conflicting = next(
                (
                    item
                    for item in self._items.values()
                    if item.package_id == package_id
                    and item.package_version == package_version
                    and (
                        item.seed_digest != seed_digest
                        or item.request_digest != request_digest
                    )
                ),
                None,
            )
            if conflicting is not None:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_CONFLICT
                )

            token = secrets.token_urlsafe(32)
            directory = self._safe_directory(operation_id)
            directory.mkdir(parents=False, exist_ok=False)
            pending = directory / "package.pending"
            final_path = directory / "package.angmoo-world"
            try:
                pending.write_bytes(content)
                pending.replace(final_path)
            except BaseException:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=EXPORT_TOKEN_TTL_SECONDS
            )
            artifact = ExportArtifact(
                operation_id=operation_id,
                owner_id=owner_id,
                token_digest=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                path=final_path,
                filename=filename,
                expires_at=expires_at,
                package_id=package_id,
                package_version=package_version,
                source_world_id=source_world_id,
                seed_digest=seed_digest,
                manifest_digest=manifest_digest,
                license_expression=license_expression,
                request_digest=request_digest,
                idempotency_key_digest=idempotency_digest,
                download_token=token,
            )
            self._items[operation_id] = artifact
            self._idempotency[idempotency_identity] = operation_id
        return artifact, token, False

    def claim(
        self, *, operation_id: str, owner_id: str, token: str
    ) -> ExportArtifact:
        with self._lock:
            artifact = self._items.get(operation_id)
        if artifact is None:
            raise WorldPackageContractError(
                WorldPackageReasonCode.DELIVERY_EXPIRED
            )
        if artifact.expires_at <= datetime.now(timezone.utc):
            self.discard(operation_id)
            raise WorldPackageContractError(
                WorldPackageReasonCode.DELIVERY_EXPIRED
            )
        supplied = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if artifact.owner_id != owner_id or not hmac.compare_digest(
            artifact.token_digest, supplied
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.DELIVERY_FORBIDDEN
            )
        if not artifact.path.is_file():
            self.discard(operation_id)
            raise WorldPackageContractError(
                WorldPackageReasonCode.DELIVERY_EXPIRED
            )
        return artifact

    def discard(self, operation_id: str) -> None:
        with self._lock:
            artifact = self._discard_locked(operation_id)
        if artifact is not None:
            shutil.rmtree(artifact.path.parent, ignore_errors=True)

    def _discard_locked(self, operation_id: str) -> ExportArtifact | None:
        artifact = self._items.pop(operation_id, None)
        if artifact is not None:
            identity = (artifact.owner_id, artifact.idempotency_key_digest)
            if self._idempotency.get(identity) == operation_id:
                self._idempotency.pop(identity, None)
        return artifact

    def cleanup_expired(self) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            expired = [
                operation_id
                for operation_id, item in self._items.items()
                if item.expires_at <= now
            ]
        for operation_id in expired:
            self.discard(operation_id)
        known = {item.path.parent for item in self._items.values()}
        for path in self._root.iterdir():
            if path.is_dir() and path not in known:
                shutil.rmtree(path, ignore_errors=True)

    def _safe_directory(self, operation_id: str) -> Path:
        if not operation_id or any(
            char not in "0123456789abcdef-" for char in operation_id
        ):
            raise ValueError("unsafe operation id")
        path = (self._root / operation_id).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("unsafe operation id") from exc
        return path


__all__ = ["ExportArtifact", "FilesystemWorldPackageExportArtifacts"]
