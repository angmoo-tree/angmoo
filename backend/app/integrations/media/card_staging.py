"""Private, bounded card-display staging with a cross-process file lease.

Only encoded display bytes enter here. No database/session or original card is
kept in the staging directory. A live importer keeps its lease through commit.
"""
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from app.config import settings

MAX_CLEANUP = 32
MIN_AGE_SECONDS = 3600
_ID = re.compile(r"[a-zA-Z0-9_-]{1,96}\Z")
_TOKEN = re.compile(r"[a-f0-9]{32}\Z")
logger = logging.getLogger(__name__)


def staging_root():
    media = settings.media_root_path.resolve()
    suffix = hashlib.sha256(str(media).encode()).hexdigest()[:16]
    root = media.parent / (".angmoo-card-import-" + suffix)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    media.mkdir(parents=True, exist_ok=True)
    if root.stat().st_dev != media.stat().st_dev:
        raise OSError("card_staging_filesystem_mismatch")
    return root.resolve()


def _lock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _destination(draft_id, token):
    if not _ID.fullmatch(draft_id) or not _TOKEN.fullmatch(token):
        raise ValueError("card_staging_identity_invalid")
    root = settings.media_root_path.resolve()
    path = (root / "drafts" / draft_id / f"avatar-card-{token}.webp").resolve()
    path.relative_to(root)
    return path, f"{settings.media_url_path}/drafts/{draft_id}/{path.name}"


@dataclass
class PreparedDisplay:
    directory: Path
    destination: Path
    url: str
    lease: object
    promoted: bool = False

    def promote(self):
        # The prepared parent already exists; never copy full bytes in a writer.
        if not self.promoted:
            (self.directory / "display.webp").replace(self.destination)
            self.promoted = True

    def finish(self, *, remove_final=False, preserve=False):
        try:
            if not preserve:
                if remove_final:
                    self.destination.unlink(missing_ok=True)
                (self.directory / "display.webp").unlink(missing_ok=True)
                (self.directory / "manifest.json").unlink(missing_ok=True)
        except OSError:
            # A successful DB commit is not a failed import merely because
            # private staging cleanup is temporarily unavailable.
            preserve = True
            logger.warning("card_staging_cleanup_deferred")
        finally:
            try:
                _unlock(self.lease)
            finally:
                self.lease.close()
        if not preserve:
            try:
                (self.directory / "lease").unlink(missing_ok=True)
                self.directory.rmdir()
            except OSError:
                logger.warning("card_staging_cleanup_deferred")


def prepare_display(*, draft_id: str, encoded: bytes) -> PreparedDisplay:
    token = uuid4().hex
    destination, url = _destination(draft_id, token)
    directory = staging_root() / token
    directory.mkdir(mode=0o700)
    lease = (directory / "lease").open("x+b")
    lease.write(b"1"); lease.flush(); _lock(lease)
    prepared = PreparedDisplay(directory, destination, url, lease)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_text(json.dumps({"draft_id": draft_id}), encoding="utf-8")
        display_path = directory / "display.webp"
        display_path.write_bytes(encoded)
        with display_path.open("r+b") as stream:
            os.fsync(stream.fileno())
        return prepared
    except BaseException:
        prepared.finish()
        raise


def cleanup_staging(is_referenced, *, now=None):
    """Age is only a filter. Lease + canonical reference decide deletion."""
    now = time.time() if now is None else now
    root = staging_root()
    scanned = 0
    with os.scandir(root) as entries:
        for entry in entries:
            if scanned >= MAX_CLEANUP:
                break
            scanned += 1
            if not _TOKEN.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):
                continue
            directory = Path(entry.path)
            if now - directory.stat().st_mtime < MIN_AGE_SECONDS:
                continue
            lease = None
            locked = False
            remove_directory = False
            try:
                if any((directory / name).is_symlink() for name in ("lease", "manifest.json", "display.webp")):
                    continue
                lease_path = directory / "lease"
                try:
                    lease = lease_path.open("r+b")
                except FileNotFoundError:
                    lease = lease_path.open("x+b")
                    lease.write(b"1"); lease.flush()
                _lock(lease); locked = True
                manifest_path = directory / "manifest.json"
                if not manifest_path.exists():
                    # A crash before preparing the manifest cannot have
                    # promoted a final file. Only our bounded private files go.
                    (directory / "display.webp").unlink(missing_ok=True)
                    remove_directory = True
                    continue
                if manifest_path.stat().st_size > 512:
                    continue
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                destination, url = _destination(manifest["draft_id"], entry.name)
                # Live requests cannot promote or commit while this lease is held.
                referenced = is_referenced(url)
                if not referenced:
                    destination.unlink(missing_ok=True)
                (directory / "display.webp").unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                remove_directory = True
            except (OSError, ValueError, KeyError, TypeError):
                continue
            finally:
                if lease:
                    if locked:
                        _unlock(lease)
                    lease.close()
                if remove_directory:
                    try:
                        (directory / "lease").unlink(missing_ok=True)
                        directory.rmdir()
                    except OSError:
                        pass
