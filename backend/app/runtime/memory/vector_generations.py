"""Crash-safe pointers for disposable vector generations; canonical is untouched."""
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError


class VectorGenerations:
    def __init__(self, root: Path, index_factory):
        self.root, self._factory = root, index_factory
        self.marker = root / "current.json"
        self.state = {"version": 1, "active": "v1", "staging": None, "previous": None}

    def _index(self, generation):
        if not isinstance(generation, str) or not re.fullmatch(r"v1|g-[a-f0-9]{32}", generation):
            raise MemoryVectorProjectionError("memory_vector_generation_invalid")
        return self._factory(self.root / "generations" / generation / "vectors.sqlite3", generation=generation)

    def _save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.marker.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.marker)

    def open(self):
        had_marker = self.marker.exists()
        if had_marker:
            try:
                value = json.loads(self.marker.read_text(encoding="utf-8"))
                if set(value) != set(self.state) or value["version"] != 1:
                    raise ValueError()
                self.state = value
            except (ValueError, TypeError):
                raise MemoryVectorProjectionError("memory_vector_generation_invalid") from None
        active = self._index(self.state["active"])
        try:
            if had_marker and not active.database_path.exists():
                raise MemoryVectorProjectionError("memory_vector_generation_missing")
            active.open()
        except MemoryVectorProjectionError:
            # Preserve failed files. Reconstruct only durable registered content.
            active = None
            if self.state["staging"] is None:
                self.state["staging"] = "g-" + uuid4().hex
                self._save()
        staging = None
        if self.state["staging"] is not None:
            staging = self._index(self.state["staging"])
            staging.open()
        if not had_marker:
            self._save()
        return active, staging

    def promote(self, index):
        if self.state["staging"] != index.generation:
            raise MemoryVectorProjectionError("memory_vector_generation_changed")
        index.open()
        self.state = {"version": 1, "active": index.generation,
                      "previous": self.state["active"], "staging": None}
        self._save()
