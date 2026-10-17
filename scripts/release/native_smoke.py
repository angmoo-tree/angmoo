"""Synthetic, offline native execution inside the actual backend candidate."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import sqlite3
import tempfile
from time import monotonic

import ladybug

from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument, MemoryVectorQuery
from app.runtime.memory.vector_resources import bundled_vector_index
from app.runtime.memory.sqlite_vec1 import VectorCancellation
from app.runtime.memory.vector_worker import VectorReadWorkers


def main():
    with tempfile.TemporaryDirectory(prefix="angmoo-native-") as directory:
        root = Path(directory)
        db = sqlite3.connect(root / "fts.sqlite3")
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.execute("CREATE VIRTUAL TABLE evidence USING fts5(body)")
        db.execute("INSERT INTO evidence VALUES ('angmoo native search')")
        db.commit()
        assert db.execute("SELECT count(*) FROM evidence WHERE evidence MATCH 'angmoo'").fetchone()[0] == 1
        db.close()
        graph = ladybug.Database(str(root / "graph"))
        connection = ladybug.Connection(graph)
        connection.execute("CREATE NODE TABLE Item(id STRING, PRIMARY KEY(id))")
        connection.execute("CREATE (:Item {id: 'synthetic'})")
        assert connection.execute("MATCH (n:Item) RETURN count(n)").get_next()[0] == 1
        connection.close()
        graph.close()
        graph = ladybug.Database(str(root / "graph"))
        connection = ladybug.Connection(graph)
        assert connection.execute("MATCH (n:Item) RETURN n.id").get_next()[0] == "synthetic"
        connection.close()
        graph.close()
        index = bundled_vector_index(root / "vectors.sqlite3")
        assert "version 0.7" in index.open()
        # Target ELF must match the running process; a host .so cannot substitute.
        elf = index._extension.read_bytes()
        assert elf[:4] == b"\x7fELF"
        machine = int.from_bytes(elf[18:20], "little")
        assert machine == {"aarch64": 183, "x86_64": 62}[platform.machine()]
        scope = MemoryScope("synthetic-owner", "synthetic-world", "synthetic-self")
        vector = [1.0] + [0.0] * 767
        profile = "gemini-embedding-2.768.cos.v1"
        index.upsert((MemoryVectorDocument("one", "one", scope, 1, "a" * 64, profile, vector, datetime.now(timezone.utc)),))
        query = MemoryVectorQuery(scope, profile, vector)
        assert index.search(query, cancellation=VectorCancellation(monotonic() + 30)).hits[0].document_id == "one"
        workers = VectorReadWorkers(database_path=index.database_path, extension_path=index._extension, extension_sha256=hashlib.sha256(elf).hexdigest())
        result = asyncio.run(workers.search(query, deadline=monotonic() + 30))
        assert result.hits[0].document_id == "one"
        assert not workers.active_processes
    print(json.dumps({"status": "PASS", "architecture": platform.machine(), "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "sqlite_fts5": True, "ladybug_restart": True, "vec1_nn": True, "spawned_search_worker": True, "external_ai_calls": 0}))


if __name__ == "__main__":
    main()
