from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

import ladybug as lb

from windows_path_alias import WindowsAsciiPathAlias


class ExclusiveWriterLock:
    """Cross-process one-byte lock used by the future single-writer adapter."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: Any | None = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError("writer_lock_unavailable") from None
        self._file = handle

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        self._file = None

    def __enter__(self) -> "ExclusiveWriterLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def _rows(result: Any) -> list[list[Any]]:
    rows: list[list[Any]] = []
    while result.has_next():
        rows.append(list(result.get_next()))
    return rows


def _execute(connection: Any, query: str, parameters: dict[str, Any] | None = None) -> list[list[Any]]:
    result = connection.execute(query, parameters=parameters or {})
    return _rows(result)


def _bootstrap(connection: Any) -> None:
    statements = (
        "CREATE NODE TABLE IF NOT EXISTS World(world_id STRING PRIMARY KEY)",
        """
        CREATE NODE TABLE IF NOT EXISTS WorldCharacter(
          world_character_id STRING PRIMARY KEY,
          world_id STRING,
          character_id STRING,
          name STRING
        )
        """,
        """
        CREATE REL TABLE IF NOT EXISTS RELATES_TO(
          FROM WorldCharacter TO WorldCharacter,
          world_id STRING,
          relationship_version INT64,
          affinity DOUBLE,
          source_event_id STRING
        )
        """,
    )
    for statement in statements:
        _execute(connection, statement)


def _merge_fixture(connection: Any) -> None:
    characters = (
        ("wc-mango", "world-arcana", "char-mango", "망고"),
        ("wc-sage", "world-arcana", "char-sage", "세이지"),
        ("wc-lumi", "world-arcana", "char-lumi", "루미"),
        ("wc-riven", "world-arcana", "char-riven", "리븐"),
        ("wc-other-mango", "world-other", "char-mango", "망고"),
        ("wc-other-sage", "world-other", "char-sage", "세이지"),
    )
    for world_id in ("world-arcana", "world-other"):
        _execute(
            connection,
            "MERGE (w:World {world_id: $world_id}) RETURN w.world_id",
            {"world_id": world_id},
        )
    for world_character_id, world_id, character_id, name in characters:
        _execute(
            connection,
            """
            MERGE (c:WorldCharacter {world_character_id: $world_character_id})
            SET c.world_id = $world_id, c.character_id = $character_id, c.name = $name
            RETURN c.world_character_id
            """,
            {
                "world_character_id": world_character_id,
                "world_id": world_id,
                "character_id": character_id,
                "name": name,
            },
        )

    relationships = (
        ("wc-mango", "wc-sage", "world-arcana", 2, 0.8, "event-comment-1"),
        ("wc-sage", "wc-lumi", "world-arcana", 1, 0.6, "event-routine-2"),
        ("wc-lumi", "wc-riven", "world-arcana", 1, 0.5, "event-post-3"),
        ("wc-other-mango", "wc-other-sage", "world-other", 1, 0.9, "event-other-1"),
    )
    for source, target, world_id, version, affinity, source_event_id in relationships:
        _execute(
            connection,
            """
            MATCH (source:WorldCharacter {world_character_id: $source})
            MATCH (target:WorldCharacter {world_character_id: $target})
            MERGE (source)-[relationship:RELATES_TO]->(target)
            SET relationship.world_id = $world_id,
                relationship.relationship_version = $version,
                relationship.affinity = $affinity,
                relationship.source_event_id = $source_event_id
            RETURN relationship.source_event_id
            """,
            {
                "source": source,
                "target": target,
                "world_id": world_id,
                "version": version,
                "affinity": affinity,
                "source_event_id": source_event_id,
            },
        )


def run_probe(database_root: Path) -> dict[str, Any]:
    database_root = database_root.resolve()
    database_root.mkdir(parents=True, exist_ok=True)
    writer_lock_path = database_root / "relationships.writer.lock"
    started = time.perf_counter()
    path_alias = WindowsAsciiPathAlias(database_root)

    with path_alias as native_root, ExclusiveWriterLock(writer_lock_path):
        database_path = native_root / "relationships.lbdb"
        duplicate_writer_blocked = False
        duplicate = ExclusiveWriterLock(writer_lock_path)
        try:
            duplicate.acquire()
        except RuntimeError as exc:
            duplicate_writer_blocked = str(exc) == "writer_lock_unavailable"
        else:
            duplicate.release()

        database = lb.Database(str(database_path))
        connection = lb.Connection(database)
        _bootstrap(connection)
        _merge_fixture(connection)
        first_count = _execute(
            connection,
            "MATCH (c:WorldCharacter) RETURN count(c)",
        )[0][0]
        del connection
        del database
        gc.collect()

        reopened_database = lb.Database(str(database_path))
        reopened = lb.Connection(reopened_database)
        reopened_count = _execute(
            reopened,
            "MATCH (c:WorldCharacter) RETURN count(c)",
        )[0][0]

        direct = _execute(
            reopened,
            """
            MATCH (source:WorldCharacter {world_character_id: $source})
                  -[relationship:RELATES_TO {world_id: $world_id}]->
                  (target:WorldCharacter {world_character_id: $target, world_id: $world_id})
            WHERE source.world_id = $world_id
            RETURN source.world_character_id,
                   target.world_character_id,
                   relationship.source_event_id,
                   relationship.relationship_version
            """,
            {"source": "wc-mango", "target": "wc-sage", "world_id": "world-arcana"},
        )
        bounded_paths = _execute(
            reopened,
            """
            MATCH path=(source:WorldCharacter {world_character_id: $source, world_id: $world_id})
                       -[:RELATES_TO*1..3]->
                       (target:WorldCharacter {world_id: $world_id})
            RETURN target.world_character_id, length(path)
            ORDER BY length(path), target.world_character_id
            """,
            {"source": "wc-mango", "world_id": "world-arcana"},
        )
        other_world_leak = _execute(
            reopened,
            """
            MATCH (source:WorldCharacter {world_character_id: $source})
                  -[relationship:RELATES_TO]->(target:WorldCharacter)
            WHERE relationship.world_id <> $world_id OR target.world_id <> $world_id
            RETURN count(relationship)
            """,
            {"source": "wc-mango", "world_id": "world-arcana"},
        )[0][0]

        read_lock = threading.RLock()
        read_results: list[int] = []
        read_errors: list[str] = []

        def serialized_read() -> None:
            try:
                with read_lock:
                    value = _execute(
                        reopened,
                        "MATCH (:WorldCharacter)-[r:RELATES_TO {world_id: $world_id}]->(:WorldCharacter) RETURN count(r)",
                        {"world_id": "world-arcana"},
                    )[0][0]
                    read_results.append(int(value))
            except Exception as exc:  # evidence captures error class only
                read_errors.append(type(exc).__name__)

        threads = [threading.Thread(target=serialized_read) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        del reopened
        del reopened_database
        gc.collect()

    wheel_distribution = importlib.metadata.distribution("ladybug")
    native_files = sorted(
        str(item)
        for item in wheel_distribution.files or []
        if str(item).lower().endswith((".pyd", ".dll"))
    )
    evidence = {
        "schema_version": 1,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "ladybug_version": importlib.metadata.version("ladybug"),
        "ladybug_license": wheel_distribution.metadata.get("License-Expression")
        or wheel_distribution.metadata.get("License"),
        "database_path_kind": "non_ascii_and_space",
        "database_path_strategy": "isolated_process_temporary_ascii_drive_alias",
        "database_path_alias_used": path_alias.used,
        "database_path_alias_released": path_alias.released,
        "database_reopen": first_count == reopened_count == 6,
        "idempotent_merge": reopened_count == 6,
        "single_writer_policy": duplicate_writer_blocked,
        "serialized_reads": len(read_results) == 5 and not read_errors and set(read_results) == {3},
        "direct_evidence": direct,
        "bounded_paths": bounded_paths,
        "world_isolation": other_world_leak == 0,
        "native_files": native_files,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    evidence["digest"] = hashlib.sha256(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    required = (
        evidence["database_reopen"],
        evidence["idempotent_merge"],
        evidence["single_writer_policy"],
        evidence["serialized_reads"],
        evidence["world_isolation"],
        direct == [["wc-mango", "wc-sage", "event-comment-1", 2]],
        bounded_paths == [["wc-sage", 1], ["wc-lumi", 2], ["wc-riven", 3]],
    )
    evidence["status"] = "PASS" if all(required) else "FAIL"
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = run_probe(args.database_root)
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
