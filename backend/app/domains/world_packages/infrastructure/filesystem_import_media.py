"""Operation-owned media promotion journal for World Package imports."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import shutil
import threading

from app.domains.world_packages.domain.canonical import canonical_json_bytes
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.preview import (
    WorldPackageNormalizedAsset,
    WorldPackageNormalizedAssetPayload,
)
from app.domains.world_packages.domain.seed import WorldPackageImportedAsset


_FILESYSTEM_LOCK = threading.RLock()


class FilesystemWorldPackageImportMedia:
    """Promote only files named in an import-owned canonical journal."""

    def __init__(
        self,
        *,
        media_root: Path,
        runtime_root: Path,
        media_url_path: str = "/media",
    ) -> None:
        self._media_root = media_root.resolve()
        self._stage_root = (
            self._media_root / ".world-package-import-staging"
        ).resolve()
        self._final_root = (
            self._media_root / "world-package-imports"
        ).resolve()
        self._journal_root = (
            runtime_root.resolve()
            / "world-packages"
            / "import-media-journal"
        ).resolve()
        self._url_prefix = "/" + media_url_path.strip("/")
        for path in (self._stage_root, self._final_root, self._journal_root):
            path.mkdir(parents=True, exist_ok=True)

    def prepare(
        self,
        *,
        import_id: str,
        metadata: tuple[WorldPackageNormalizedAsset, ...],
        payloads: tuple[WorldPackageNormalizedAssetPayload, ...],
    ) -> tuple[WorldPackageImportedAsset, ...]:
        self._safe_id(import_id)
        metadata_by_ref = {item.source_ref: item for item in metadata}
        payload_by_ref = {item.source_ref: item for item in payloads}
        if set(metadata_by_ref) != set(payload_by_ref):
            raise WorldPackageContractError(
                WorldPackageReasonCode.INTEGRITY_MISMATCH
            )
        stage = self._owned_directory(self._stage_root, import_id)
        final = self._owned_directory(self._final_root, import_id)
        journal = self._journal_path(import_id)
        with _FILESYSTEM_LOCK:
            if stage.exists() or final.exists() or journal.exists():
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_CONFLICT
                )
            stage.mkdir(mode=0o700, parents=False, exist_ok=False)
            imported: list[WorldPackageImportedAsset] = []
            files: list[str] = []
            try:
                for source_ref in sorted(metadata_by_ref):
                    item = metadata_by_ref[source_ref]
                    payload = payload_by_ref[source_ref]
                    content = payload.content
                    if (
                        payload.normalized_ref != item.normalized_ref
                        or payload.normalized_sha256
                        != item.normalized_sha256
                        or len(content) != item.normalized_bytes
                        or hashlib.sha256(content).hexdigest()
                        != item.normalized_sha256
                    ):
                        raise WorldPackageContractError(
                            WorldPackageReasonCode.INTEGRITY_MISMATCH
                        )
                    filename = f"sha256-{item.normalized_sha256}.webp"
                    if Path(item.normalized_ref).name != filename:
                        raise WorldPackageContractError(
                            WorldPackageReasonCode.PATH_UNSAFE
                        )
                    destination = (stage / filename).resolve()
                    self._assert_inside(destination, stage)
                    destination.write_bytes(content)
                    files.append(filename)
                    imported.append(
                        WorldPackageImportedAsset(
                            source_ref=source_ref,
                            local_url=(
                                f"{self._url_prefix}/world-package-imports/"
                                f"{import_id}/{filename}"
                            ),
                            sha256=item.normalized_sha256,
                        )
                    )
                self._write_journal(
                    import_id=import_id,
                    state="prepared",
                    files=files,
                )
                return tuple(imported)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                journal.unlink(missing_ok=True)
                raise

    def promote(self, *, import_id: str) -> None:
        with _FILESYSTEM_LOCK:
            journal = self._read_journal(import_id)
            if journal["state"] != "prepared":
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_CONFLICT
                )
            stage = self._owned_directory(self._stage_root, import_id)
            final = self._owned_directory(self._final_root, import_id)
            if not stage.is_dir() or final.exists():
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_CONFLICT
                )
            stage.replace(final)
            self._write_journal(
                import_id=import_id,
                state="promoted",
                files=list(journal["files"]),
            )

    def mark_committed(self, *, import_id: str) -> None:
        with _FILESYSTEM_LOCK:
            journal = self._read_journal(import_id)
            if journal["state"] != "promoted":
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_FAILED
                )
            final = self._owned_directory(self._final_root, import_id)
            if not final.is_dir():
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_FAILED
                )
            self._journal_path(import_id).unlink(missing_ok=True)

    def rollback(self, *, import_id: str) -> None:
        """Delete only paths proven to belong to the exact journal/import ID."""

        with _FILESYSTEM_LOCK:
            journal_path = self._journal_path(import_id)
            if not journal_path.is_file():
                return
            self._read_journal(import_id)
            shutil.rmtree(
                self._owned_directory(self._stage_root, import_id),
                ignore_errors=True,
            )
            shutil.rmtree(
                self._owned_directory(self._final_root, import_id),
                ignore_errors=True,
            )
            journal_path.unlink(missing_ok=True)

    def recover(self, *, import_exists: Callable[[str], bool]) -> None:
        """Finalize committed promotions and remove uncommitted owned debris."""

        with _FILESYSTEM_LOCK:
            for journal_path in sorted(self._journal_root.glob("*.json")):
                import_id = journal_path.stem
                try:
                    self._safe_id(import_id)
                    journal = self._read_journal(import_id)
                except (ValueError, WorldPackageContractError):
                    continue
                committed = import_exists(import_id)
                final = self._owned_directory(self._final_root, import_id)
                if committed and journal["state"] == "promoted" and final.is_dir():
                    journal_path.unlink(missing_ok=True)
                    shutil.rmtree(
                        self._owned_directory(self._stage_root, import_id),
                        ignore_errors=True,
                    )
                    continue
                if not committed:
                    self.rollback(import_id=import_id)

    def _write_journal(
        self, *, import_id: str, state: str, files: list[str]
    ) -> None:
        payload = {
            "schema_version": "world-package-import-media-journal-v1",
            "import_id": import_id,
            "state": state,
            "files": sorted(files),
        }
        journal = self._journal_path(import_id)
        pending = journal.with_suffix(".pending")
        pending.write_bytes(canonical_json_bytes(payload))
        pending.replace(journal)

    def _read_journal(self, import_id: str) -> dict[str, object]:
        path = self._journal_path(import_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            ) from exc
        if (
            payload.get("schema_version")
            != "world-package-import-media-journal-v1"
            or payload.get("import_id") != import_id
            or payload.get("state") not in {"prepared", "promoted"}
            or not isinstance(payload.get("files"), list)
            or any(
                not isinstance(item, str)
                or not item.startswith("sha256-")
                or not item.endswith(".webp")
                for item in payload["files"]
            )
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            )
        return payload

    def _journal_path(self, import_id: str) -> Path:
        self._safe_id(import_id)
        path = (self._journal_root / f"{import_id}.json").resolve()
        self._assert_inside(path, self._journal_root)
        return path

    def _owned_directory(self, root: Path, import_id: str) -> Path:
        self._safe_id(import_id)
        path = (root / import_id).resolve()
        self._assert_inside(path, root)
        return path

    @staticmethod
    def _safe_id(value: str) -> None:
        if not value or any(ch not in "0123456789abcdef-" for ch in value):
            raise ValueError("unsafe import id")

    @staticmethod
    def _assert_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("import media path escapes owned root") from exc


__all__ = ["FilesystemWorldPackageImportMedia"]
