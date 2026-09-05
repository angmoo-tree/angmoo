"""Managed file paths and reversible quarantine shared by deletion workflows."""
from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Iterable
from uuid import uuid4

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.integrations.media.images import _content_type_from_suffix


class PrivateMediaCleanupError(Exception):
    pass


@dataclass
class PrivateMediaQuarantine:
    root: Path | None = None
    entries: list[tuple[Path, Path]] = field(default_factory=list)

    def restore(self) -> None:
        errors: list[OSError] = []
        for source, quarantined in reversed(self.entries):
            if not quarantined.exists():
                continue
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                quarantined.replace(source)
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise PrivateMediaCleanupError("private_media_restore_failed") from errors[0]
        self._remove_empty_root()

    def purge(self) -> None:
        if self.root is None or not self.root.exists():
            return
        try:
            shutil.rmtree(self.root)
        except OSError as exc:
            raise PrivateMediaCleanupError("private_media_purge_failed") from exc

    def _remove_empty_root(self) -> None:
        if self.root is None or not self.root.exists():
            return
        try:
            shutil.rmtree(self.root)
        except OSError:
            return


def quarantine_private_media(paths: Iterable[Path]) -> PrivateMediaQuarantine:
    media_root = settings.media_root_path.resolve()
    candidates: list[Path] = []
    for path in paths:
        if path.is_symlink():
            raise PrivateMediaCleanupError("private_media_symlink_not_allowed")
        resolved = path.resolve()
        try:
            resolved.relative_to(media_root)
        except ValueError as exc:
            raise PrivateMediaCleanupError("private_media_path_outside_root") from exc
        if resolved == media_root or not resolved.exists():
            continue
        candidates.append(resolved)

    selected: list[Path] = []
    for candidate in sorted(set(candidates), key=lambda item: len(item.parts)):
        if any(candidate == parent or parent in candidate.parents for parent in selected):
            continue
        selected.append(candidate)

    if not selected:
        return PrivateMediaQuarantine()

    quarantine_root = (
        media_root.parent
        / f".{media_root.name}-deletion-quarantine"
        / uuid4().hex
    )
    result = PrivateMediaQuarantine(root=quarantine_root)
    try:
        for source in selected:
            relative = source.relative_to(media_root)
            destination = quarantine_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            result.entries.append((source, destination))
    except OSError as exc:
        try:
            result.restore()
        except PrivateMediaCleanupError:
            pass
        raise PrivateMediaCleanupError("private_media_quarantine_failed") from exc
    return result


def media_url_to_path(media_url: str):
    return _media_url_to_path(media_url)


def resolve_private_media_file(
    media_url: str,
    *,
    expected_directory: str,
) -> tuple[Path, str]:
    url_prefix = f"{settings.media_url_path}/"
    if not media_url.startswith(url_prefix):
        raise InvalidProfileMediaError("Invalid private media URL")
    relative = media_url[len(url_prefix):]
    lexical_path = settings.media_root_path / Path(relative)
    expected_root = settings.media_root_path / expected_directory
    try:
        lexical_path.relative_to(expected_root)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid private media path") from exc
    current = lexical_path
    while current != expected_root:
        if current.is_symlink():
            raise InvalidProfileMediaError("Private media symlinks are not allowed")
        current = current.parent
    resolved = lexical_path.resolve()
    try:
        resolved.relative_to(expected_root.resolve())
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid private media path") from exc
    if not resolved.is_file():
        raise InvalidProfileMediaError("Private media was not found")
    return resolved, _content_type_from_suffix(resolved.suffix.lower())


def delete_media_url(media_url: str | None) -> None:
    if not media_url:
        return
    try:
        path = _media_url_to_path(media_url)
    except InvalidProfileMediaError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _media_url_to_path(media_url: str):
    url_prefix = f"{settings.media_url_path}/"
    if not media_url.startswith(url_prefix):
        raise InvalidProfileMediaError("Invalid media URL")
    relative = media_url[len(url_prefix):]
    path = (settings.media_root_path / relative).resolve()
    root = settings.media_root_path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid media path") from exc
    return path
