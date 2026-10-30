"""Bounded private received-result files; owners supply identity and validation.

The per-World file lock orders publication against permanent erasure. A closed
World can never acquire new content, even after a late provider response. This
module knows no ORM, provider, permission or retry policy.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import re
from app.core.atomic_json import locked_json, write_json


class ResultJournalError(ValueError):
    pass


class ResultJournal:
    MAX_BYTES = 256 * 1024
    MAX_FILES = 512
    MAX_TOTAL = 16 * 1024 * 1024

    def __init__(self, root, namespace):
        if not re.fullmatch(r"[a-z-]{1,40}", namespace):
            raise ResultJournalError("result_journal_namespace_invalid")
        self.root = Path(root).resolve() / namespace

    @staticmethod
    def _key(value):
        if not isinstance(value, str) or not 0 < len(value) <= 200:
            raise ResultJournalError("result_journal_identity_invalid")
        return sha256(value.encode()).hexdigest()

    @contextmanager
    def _world(self, world_id):
        path = self.root / self._key(world_id)
        for candidate in (self.root, path):
            if candidate.is_symlink() or candidate.resolve() != candidate:
                raise ResultJournalError("result_journal_path_invalid")
            candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
        with locked_json(path / "owner"):
            yield path

    def _path(self, directory, item_id):
        path = directory / (self._key(item_id) + ".json")
        if path.is_symlink() or path.resolve() != path:
            raise ResultJournalError("result_journal_path_invalid")
        return path

    def read(self, world_id, item_id):
        if (self.root / "erased" / (self._key(item_id) + ".json")).exists():
            return None
        with self._world(world_id) as directory:
            path = self._path(directory, item_id)
            if (directory / "closed.json").exists() or not path.exists():
                return None
            if path.stat().st_size > self.MAX_BYTES:
                raise ResultJournalError("result_journal_corrupt")
            try:
                envelope = json.loads(path.read_text("utf-8"))
                payload = envelope["payload"]
                if (envelope["world_id"], envelope["item_id"], envelope["digest"]) != (
                    world_id, item_id, self._digest(payload)):
                    raise ValueError()
                return payload
            except (ValueError, KeyError, TypeError, RecursionError, UnicodeError):
                raise ResultJournalError("result_journal_corrupt") from None

    @staticmethod
    def _digest(payload):
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()

    def write(self, world_id, item_id, payload):
        # The short namespace lock orders individual privacy erasure against a
        # late response even when its canonical row has already disappeared.
        with self._items() as erased:
            if self._path(erased, item_id).exists():
                raise ResultJournalError("result_journal_item_closed")
            self._write(world_id, item_id, payload)

    @contextmanager
    def _items(self):
        path = self.root / "erased"
        if path.is_symlink() or path.resolve() != path:
            raise ResultJournalError("result_journal_path_invalid")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        with locked_json(path / "owner"):
            yield path

    def close_item(self, item_id):
        with self._items() as erased:
            marker = self._path(erased, item_id)
            if not marker.exists():
                write_json(marker, {"closed": True})
            self.remove_item(item_id)

    def _write(self, world_id, item_id, payload):
        envelope = dict(world_id=world_id, item_id=item_id, payload=payload, digest=self._digest(payload))
        size = len(json.dumps(envelope, ensure_ascii=True, allow_nan=False).encode())
        if size > self.MAX_BYTES:
            raise ResultJournalError("result_journal_capacity")
        with self._world(world_id) as directory:
            if (directory / "closed.json").exists():
                raise ResultJournalError("result_journal_world_closed")
            path = self._path(directory, item_id)
            files = tuple(directory.glob("*.json"))
            if (len(files) - int(path.exists()) >= self.MAX_FILES or
                sum(p.stat().st_size for p in files if p != path) + size > self.MAX_TOTAL):
                raise ResultJournalError("result_journal_capacity")
            # Rejected provider text may contain an unpaired surrogate. Escape
            # its code point losslessly rather than failing to preserve it.
            write_json(path, envelope, ensure_ascii=True)

    def remove(self, world_id, item_id, *, expected_payload=None):
        with self._world(world_id) as directory:
            path = self._path(directory, item_id)
            if expected_payload is not None and path.exists():
                if path.stat().st_size > self.MAX_BYTES:
                    raise ResultJournalError("result_journal_corrupt")
                try:
                    envelope = json.loads(path.read_text("utf-8"))
                    if envelope["digest"] != self._digest(expected_payload) or envelope["payload"] != expected_payload:
                        return False
                except (ValueError, KeyError, TypeError, UnicodeError):
                    raise ResultJournalError("result_journal_corrupt") from None
            path.unlink(missing_ok=True)
            return True

    def quarantine(self, world_id, item_id, payload, *, reason):
        """Keep unusable evidence outside replay, with the same privacy fences."""
        with self._world(world_id) as directory:
            if (directory / "closed.json").exists():
                raise ResultJournalError("result_journal_world_closed")
            rejected = ResultJournal(self.root.parent, self.root.name + "-rejected")
            previous = rejected.read(world_id, item_id)
            entry = {"reason": reason, "record": payload}
            if previous and previous.get("record") != payload:
                entry["history"] = [*previous.get("history", []), {k: v for k, v in previous.items() if k != "history"}]
            elif previous:
                entry = previous
            rejected.write(world_id, item_id, entry)
            self._path(directory, item_id).unlink(missing_ok=True)

    def close_world(self, world_id):
        with self._world(world_id) as directory:
            # Commit a content-free fence before removing content. A crash is
            # replayable and cannot reopen admission for an old request.
            if not (directory / "closed.json").exists():
                write_json(directory / "closed.json", {"closed": True})
            for path in directory.iterdir():
                if re.fullmatch(r"[a-f0-9]{64}\.json(?:\..+\.tmp)?", path.name):
                    if path.is_symlink() or path.resolve() != path:
                        raise ResultJournalError("result_journal_path_invalid")
                    path.unlink(missing_ok=True)

    def remove_item(self, item_id):
        """Privacy cleanup knows the stable item ID even after canonical purge."""
        if not self.root.exists():
            return
        for directory in self.root.iterdir():
            if not re.fullmatch(r"[a-f0-9]{64}", directory.name):
                continue
            if directory.is_symlink() or directory.resolve() != directory:
                raise ResultJournalError("result_journal_path_invalid")
            with locked_json(directory / "owner"):
                self._path(directory, item_id).unlink(missing_ok=True)
