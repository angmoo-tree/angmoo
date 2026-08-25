"""Process-owned, expiring filesystem staging for untrusted packages."""

from __future__ import annotations

from collections.abc import AsyncIterable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import shutil
import threading

from app.domains.world_packages.domain.canonical import canonical_json_bytes
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.import_state import WorldPackageImportState
from app.domains.world_packages.domain.package_policy import WorldPackagePolicy
from app.domains.world_packages.domain.preview import (
    WorldPackageImportPreview,
    WorldPackagePreparedPreview,
)


@dataclass(slots=True)
class _StagingOperation:
    operation_id: str
    owner_id: str
    state: WorldPackageImportState
    directory: Path
    created_at: datetime
    expires_at: datetime | None = None
    archive_digest: str | None = None
    content_digest: str | None = None
    token_digest: str | None = None
    preview: WorldPackageImportPreview | None = None
    preview_token: str | None = field(default=None, repr=False)


class FilesystemWorldPackageStaging:
    """Own staging for one backend process and discard previous-process debris."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._root = (runtime_root / "world-packages" / "staging").resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._items: dict[str, _StagingOperation] = {}
        self._lock = threading.RLock()
        self.cleanup_startup_orphans()

    @property
    def root(self) -> Path:
        return self._root

    async def receive(
        self,
        *,
        operation_id: str,
        owner_id: str,
        chunks: AsyncIterable[bytes],
    ) -> None:
        self.cleanup_expired()
        directory = self._safe_directory(operation_id)
        created_at = self._aware_utc(self._clock())
        operation = _StagingOperation(
            operation_id=operation_id,
            owner_id=owner_id,
            state=WorldPackageImportState.RECEIVING,
            directory=directory,
            created_at=created_at,
        )
        with self._lock:
            if operation_id in self._items or directory.exists():
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_CONFLICT
                )
            directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            self._items[operation_id] = operation
        self._write_operation(operation)

        pending = directory / "upload.pending"
        final_path = directory / "upload.angmoo-world"
        received = 0
        digest = hashlib.sha256()
        try:
            with pending.open("xb") as target:
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise TypeError("package upload chunks must be bytes")
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > WorldPackagePolicy.MAX_COMPRESSED_BYTES:
                        raise WorldPackageContractError(
                            WorldPackageReasonCode.UPLOAD_TOO_LARGE
                        )
                    target.write(chunk)
                    digest.update(chunk)
            if received == 0:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.ARCHIVE_INVALID
                )
            pending.replace(final_path)
            operation.state = WorldPackageImportState.RECEIVED
            operation.archive_digest = digest.hexdigest()
            self._write_operation(operation)
        except BaseException:
            self._remove(operation_id)
            raise

    def transition(
        self,
        *,
        operation_id: str,
        owner_id: str,
        state: WorldPackageImportState,
    ) -> None:
        operation = self._owned(operation_id, owner_id)
        allowed = {
            WorldPackageImportState.RECEIVED: WorldPackageImportState.VALIDATING,
        }
        if allowed.get(operation.state) is not state:
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_CONFLICT
            )
        operation.state = state
        self._write_operation(operation)

    def publish_preview(
        self,
        *,
        owner_id: str,
        preview: WorldPackageImportPreview,
    ) -> WorldPackagePreparedPreview:
        operation = self._owned(preview.operation_id, owner_id)
        if operation.state is not WorldPackageImportState.VALIDATING:
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_CONFLICT
            )
        if operation.archive_digest != preview.archive_digest:
            raise WorldPackageContractError(
                WorldPackageReasonCode.INTEGRITY_MISMATCH
            )
        token = secrets.token_urlsafe(32)
        token_digest = self._bound_token_digest(
            token=token,
            operation_id=preview.operation_id,
            owner_id=owner_id,
            content_digest=preview.content_digest,
        )
        preview_path = operation.directory / "preview.json"
        pending = operation.directory / "preview.pending"
        pending.write_bytes(canonical_json_bytes(_preview_payload(preview)))
        pending.replace(preview_path)
        operation.state = WorldPackageImportState.PREVIEW_READY
        operation.expires_at = preview.expires_at
        operation.content_digest = preview.content_digest
        operation.token_digest = token_digest
        operation.preview = preview
        operation.preview_token = token
        self._write_operation(operation)
        return WorldPackagePreparedPreview(preview=preview, preview_token=token)

    def read_preview(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> WorldPackageImportPreview:
        operation = self._claim(
            operation_id=operation_id,
            owner_id=owner_id,
            preview_token=preview_token,
        )
        assert operation.preview is not None
        return operation.preview

    def discard(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> None:
        self._claim(
            operation_id=operation_id,
            owner_id=owner_id,
            preview_token=preview_token,
        )
        self._remove(operation_id)

    def reject(self, *, operation_id: str, owner_id: str) -> None:
        with self._lock:
            operation = self._items.get(operation_id)
        if operation is None:
            return
        if operation.owner_id != owner_id:
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_FORBIDDEN
            )
        operation.state = WorldPackageImportState.REJECTED
        self._write_operation(operation)
        self._remove(operation_id)

    def upload_path(self, operation_id: str) -> Path:
        path = self._safe_directory(operation_id) / "upload.angmoo-world"
        if not path.is_file():
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_EXPIRED
            )
        return path

    def extracted_path(self, operation_id: str) -> Path:
        directory = self._safe_directory(operation_id)
        extracted = (directory / "extracted").resolve()
        self._assert_inside(extracted, directory)
        if extracted.exists():
            shutil.rmtree(extracted, ignore_errors=True)
        extracted.mkdir(mode=0o700, parents=False, exist_ok=False)
        return extracted

    def cleanup_expired(self) -> None:
        now = self._aware_utc(self._clock())
        with self._lock:
            expired = [
                operation_id
                for operation_id, operation in self._items.items()
                if operation.expires_at is not None
                and operation.expires_at <= now
            ]
        for operation_id in expired:
            self._remove(operation_id)

    def cleanup_startup_orphans(self) -> None:
        with self._lock:
            self._items.clear()
        for path in self._root.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    def _claim(
        self,
        *,
        operation_id: str,
        owner_id: str,
        preview_token: str,
    ) -> _StagingOperation:
        self.cleanup_expired()
        with self._lock:
            operation = self._items.get(operation_id)
        if operation is None or operation.state is not WorldPackageImportState.PREVIEW_READY:
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_EXPIRED
            )
        if (
            operation.expires_at is None
            or operation.expires_at <= self._aware_utc(self._clock())
        ):
            self._remove(operation_id)
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_EXPIRED
            )
        if operation.content_digest is None or operation.token_digest is None:
            self._remove(operation_id)
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_EXPIRED
            )
        supplied = self._bound_token_digest(
            token=preview_token,
            operation_id=operation_id,
            owner_id=owner_id,
            content_digest=operation.content_digest,
        )
        if operation.owner_id != owner_id or not hmac.compare_digest(
            operation.token_digest, supplied
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_FORBIDDEN
            )
        if not (operation.directory / "preview.json").is_file():
            self._remove(operation_id)
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_EXPIRED
            )
        return operation

    def _owned(self, operation_id: str, owner_id: str) -> _StagingOperation:
        with self._lock:
            operation = self._items.get(operation_id)
        if operation is None:
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_EXPIRED
            )
        if operation.owner_id != owner_id:
            raise WorldPackageContractError(
                WorldPackageReasonCode.STAGE_FORBIDDEN
            )
        return operation

    def _write_operation(self, operation: _StagingOperation) -> None:
        payload = {
            "schema_version": "world-package-staging-operation-v1",
            "operation_id": operation.operation_id,
            "state": operation.state.value,
            "created_at": operation.created_at.isoformat().replace("+00:00", "Z"),
            "expires_at": (
                operation.expires_at.isoformat().replace("+00:00", "Z")
                if operation.expires_at is not None
                else None
            ),
            "archive_digest": operation.archive_digest,
            "content_digest": operation.content_digest,
        }
        pending = operation.directory / "operation.pending"
        pending.write_bytes(canonical_json_bytes(payload))
        pending.replace(operation.directory / "operation.json")

    def _remove(self, operation_id: str) -> None:
        with self._lock:
            operation = self._items.pop(operation_id, None)
        directory = (
            operation.directory
            if operation is not None
            else self._safe_directory(operation_id)
        )
        shutil.rmtree(directory, ignore_errors=True)

    def _safe_directory(self, operation_id: str) -> Path:
        if not operation_id or any(
            character not in "0123456789abcdef-" for character in operation_id
        ):
            raise ValueError("unsafe operation id")
        path = (self._root / operation_id).resolve()
        self._assert_inside(path, self._root)
        return path

    @staticmethod
    def _assert_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("staging path escapes process-owned root") from exc

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _bound_token_digest(
        *, token: str, operation_id: str, owner_id: str, content_digest: str
    ) -> str:
        payload = "\x00".join(
            (operation_id, owner_id, content_digest, token)
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def _preview_payload(preview: WorldPackageImportPreview) -> dict[str, object]:
    """Create the persisted preview without retaining the opaque token."""

    return {
        "schema_version": preview.schema_version,
        "state": preview.state.value,
        "operation_id": preview.operation_id,
        "archive_digest": preview.archive_digest,
        "content_digest": preview.content_digest,
        "package_id": preview.package_id,
        "package_version": preview.package_version,
        "producer_name": preview.producer_name,
        "producer_version": preview.producer_version,
        "min_reader_version": preview.min_reader_version,
        "world_contract_version": preview.world_contract_version,
        "trust_state": preview.trust_state.value,
        "license": preview.license.model_dump(mode="json"),
        "world_name": preview.world_name,
        "world_tagline": preview.world_tagline,
        "character_names": list(preview.character_names),
        "role_count": preview.role_count,
        "place_count": preview.place_count,
        "rule_count": preview.rule_count,
        "glossary_count": preview.glossary_count,
        "asset_count": preview.asset_count,
        "asset_bytes": preview.asset_bytes,
        "total_decoded_pixels": preview.total_decoded_pixels,
        "excluded_owner_controlled_characters": (
            preview.excluded_owner_controlled_characters
        ),
        "excluded_runtime_records": preview.excluded_runtime_records,
        "collision_plan": {
            "planned_world_slug": preview.collision_plan.planned_world_slug,
            "duplicate_state": preview.collision_plan.duplicate_state.value,
            "commit_allowed_by_default": (
                preview.collision_plan.commit_allowed_by_default
            ),
            "characters": [
                {
                    "source_ref": item.source_ref,
                    "display_name": item.display_name,
                    "planned_handle": item.planned_handle,
                }
                for item in preview.collision_plan.characters
            ],
        },
        "normalized_assets": [
            {
                "source_ref": item.source_ref,
                "normalized_ref": item.normalized_ref,
                "normalized_sha256": item.normalized_sha256,
                "normalized_bytes": item.normalized_bytes,
                "width": item.width,
                "height": item.height,
                "alt_text": item.alt_text,
            }
            for item in preview.normalized_assets
        ],
        "warnings": list(preview.warnings),
        "blocking_issues": list(preview.blocking_issues),
        "expires_at": preview.expires_at.isoformat().replace("+00:00", "Z"),
    }


__all__ = ["FilesystemWorldPackageStaging"]
