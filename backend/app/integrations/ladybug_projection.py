"""LadybugDB adapter for the replayable relationship graph projection.

SQLite remains the canonical event/outbox store. This adapter owns one
LadybugDB connection, accepts only validated relationship-domain commands, and
can be deleted and rebuilt without losing canonical user data.
"""

from __future__ import annotations

import ctypes
from datetime import datetime
import gc
import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Any

import ladybug as lb

from app.domains.relationships.ports.projection import (
    RelationshipProjectionBackendError,
)
from app.domains.relationships.projection.commands import (
    NoGraphMutationCommand,
    ProjectionCommand,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)


LADYBUG_PROJECTION_SCHEMA_VERSION = 1


class LadybugProjectionError(RelationshipProjectionBackendError):
    """Stable, sanitized LadybugDB error exposed to the projection worker."""


class _ExclusiveWriterLock:
    """Cross-process one-byte lock for the single READ_WRITE owner."""

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
            raise LadybugProjectionError("ladybug_writer_lock_unavailable") from None
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


class _WindowsAsciiPathAlias:
    """Temporarily expose a Unicode data directory through a free drive."""

    def __init__(self, target: Path) -> None:
        self.target = target.resolve()
        self.drive: str | None = None

    @staticmethod
    def _logical_drive_mask() -> int:
        return int(ctypes.windll.kernel32.GetLogicalDrives())

    @classmethod
    def _available_drive(cls) -> str:
        mask = cls._logical_drive_mask()
        for letter in "ZYXWVUTSRQPONMLKJIHGFED":
            index = ord(letter) - ord("A")
            if not mask & (1 << index):
                return f"{letter}:"
        raise LadybugProjectionError("ladybug_path_alias_unavailable")

    def open(self) -> Path:
        self.target.mkdir(parents=True, exist_ok=True)
        if os.name != "nt" or str(self.target).isascii():
            return self.target
        drive = self._available_drive()
        completed = subprocess.run(
            ["subst", drive, str(self.target)],
            check=False,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if completed.returncode != 0:
            raise LadybugProjectionError("ladybug_path_alias_create_failed")
        self.drive = drive
        return Path(f"{drive}\\")

    def close(self) -> None:
        drive = self.drive
        if drive is None:
            return
        completed = subprocess.run(
            ["subst", drive, "/D"],
            check=False,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if completed.returncode != 0:
            raise LadybugProjectionError("ladybug_path_alias_remove_failed")
        self.drive = None


_BOOTSTRAP_STATEMENTS = (
    "CREATE NODE TABLE IF NOT EXISTS ProjectionMeta("
    "id STRING PRIMARY KEY, schema_version INT64, adapter STRING)",
    "CREATE NODE TABLE IF NOT EXISTS World(world_id STRING PRIMARY KEY)",
    """
    CREATE NODE TABLE IF NOT EXISTS WorldCharacter(
      world_character_id STRING PRIMARY KEY,
      world_id STRING,
      character_id STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS SocialEvent(
      event_id STRING PRIMARY KEY,
      world_id STRING,
      event_type STRING,
      occurred_at STRING,
      schema_version STRING
    )
    """,
    "CREATE REL TABLE IF NOT EXISTS MEMBER_OF("
    "FROM WorldCharacter TO World, world_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS PERFORMED("
    "FROM WorldCharacter TO SocialEvent, world_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS TARGETED("
    "FROM SocialEvent TO WorldCharacter, world_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS OCCURRED_IN("
    "FROM SocialEvent TO World, world_id STRING)",
    """
    CREATE REL TABLE IF NOT EXISTS RELATES_TO(
      FROM WorldCharacter TO WorldCharacter,
      world_id STRING,
      relationship_state_id STRING,
      familiarity INT64,
      affinity INT64,
      trust INT64,
      tension INT64,
      interaction_count INT64,
      last_event_id STRING,
      last_event_at STRING,
      updated_at STRING,
      relationship_version INT64
    )
    """,
    """
    CREATE REL TABLE IF NOT EXISTS RELATIONSHIP_GROUNDED_IN(
      FROM WorldCharacter TO SocialEvent,
      world_id STRING,
      target_world_character_id STRING,
      relationship_state_id STRING,
      event_id STRING,
      relationship_version INT64
    )
    """,
)


def _rows(result: Any) -> list[list[Any]]:
    rows: list[list[Any]] = []
    while result.has_next():
        rows.append(list(result.get_next()))
    result.close()
    return rows


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _event_parameters(command: SocialEventProjectionCommand) -> dict[str, Any]:
    return {
        "world_id": command.world_id,
        "event_id": command.event_id,
        "event_type": command.event_type,
        "occurred_at": _datetime_text(command.occurred_at),
        "schema_version": command.schema_version,
        "actor_world_character_id": command.actor_world_character_id,
        "actor_character_id": command.actor_character_id,
        "target_world_character_id": command.target_world_character_id,
        "target_character_id": command.target_character_id,
    }


class LadybugRelationshipProjection:
    """Single-owner LadybugDB projection implementing domain write commands."""

    def __init__(self, *, database_root: Path) -> None:
        self._root = database_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._writer_lock = _ExclusiveWriterLock(
            self._root / "relationships.writer.lock"
        )
        self._path_alias = _WindowsAsciiPathAlias(self._root)
        self._access_lock = threading.RLock()
        self._database: Any | None = None
        self._connection: Any | None = None
        self._closed = False
        try:
            self._writer_lock.acquire()
            native_root = self._path_alias.open()
            self._database = lb.Database(str(native_root / "relationships.lbdb"))
            self._connection = lb.Connection(self._database)
            self.bootstrap()
        except LadybugProjectionError:
            self._cleanup_after_open_failure()
            raise
        except Exception:
            self._cleanup_after_open_failure()
            raise LadybugProjectionError("ladybug_unavailable") from None

    def _cleanup_after_open_failure(self) -> None:
        self._connection = None
        self._database = None
        gc.collect()
        try:
            self._path_alias.close()
        finally:
            self._writer_lock.release()

    def _execute(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[list[Any]]:
        connection = self._connection
        if connection is None or self._closed:
            raise LadybugProjectionError("ladybug_unavailable")
        try:
            return _rows(connection.execute(query, parameters=parameters or {}))
        except LadybugProjectionError:
            raise
        except Exception:
            raise LadybugProjectionError("ladybug_transient") from None

    def bootstrap(self) -> None:
        with self._access_lock:
            for statement in _BOOTSTRAP_STATEMENTS:
                self._execute(statement)
            self._execute(
                """
                MERGE (meta:ProjectionMeta {id: $id})
                SET meta.schema_version = $schema_version, meta.adapter = $adapter
                RETURN meta.schema_version
                """,
                {
                    "id": "relationship_projection",
                    "schema_version": LADYBUG_PROJECTION_SCHEMA_VERSION,
                    "adapter": "ladybug",
                },
            )

    def verify_connectivity(self) -> None:
        with self._access_lock:
            rows = self._execute("RETURN 1")
            if rows != [[1]]:
                raise LadybugProjectionError("ladybug_unavailable")

    def close(self) -> None:
        with self._access_lock:
            if self._closed:
                return
            self._closed = True
            self._connection = None
            self._database = None
            gc.collect()
            alias_error: LadybugProjectionError | None = None
            try:
                self._path_alias.close()
            except LadybugProjectionError as exc:
                alias_error = exc
            finally:
                self._writer_lock.release()
            if alias_error is not None:
                raise alias_error

    def __enter__(self) -> "LadybugRelationshipProjection":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _merge_event(self, command: SocialEventProjectionCommand) -> None:
        parameters = _event_parameters(command)
        self._execute(
            """
            MERGE (world:World {world_id: $world_id})
            MERGE (actor:WorldCharacter {
              world_character_id: $actor_world_character_id
            })
            SET actor.character_id = $actor_character_id,
                actor.world_id = $world_id
            MERGE (event:SocialEvent {event_id: $event_id})
            SET event.world_id = $world_id,
                event.event_type = $event_type,
                event.occurred_at = $occurred_at,
                event.schema_version = $schema_version
            MERGE (actor)-[member:MEMBER_OF]->(world)
            SET member.world_id = $world_id
            MERGE (actor)-[performed:PERFORMED]->(event)
            SET performed.world_id = $world_id
            MERGE (event)-[occurred:OCCURRED_IN]->(world)
            SET occurred.world_id = $world_id
            RETURN event.event_id
            """,
            parameters,
        )
        if command.target_world_character_id is None:
            return
        self._execute(
            """
            MATCH (world:World {world_id: $world_id})
            MATCH (event:SocialEvent {event_id: $event_id})
            MERGE (target:WorldCharacter {
              world_character_id: $target_world_character_id
            })
            SET target.character_id = $target_character_id,
                target.world_id = $world_id
            MERGE (target)-[member:MEMBER_OF]->(world)
            SET member.world_id = $world_id
            MERGE (event)-[targeted:TARGETED]->(target)
            SET targeted.world_id = $world_id
            RETURN target.world_character_id
            """,
            parameters,
        )

    def apply(
        self, command: ProjectionCommand, *, timeout_seconds: float = 5.0
    ) -> str:
        if timeout_seconds <= 0:
            raise LadybugProjectionError("ladybug_query_timeout")
        with self._access_lock:
            connection = self._connection
            if connection is None or self._closed:
                raise LadybugProjectionError("ladybug_unavailable")
            connection.set_query_timeout(max(1, int(timeout_seconds * 1000)))
            self._execute("BEGIN TRANSACTION")
            try:
                result = self._apply_in_transaction(
                    command, timeout_seconds=timeout_seconds
                )
                self._execute("COMMIT")
                return result
            except Exception:
                try:
                    self._execute("ROLLBACK")
                except LadybugProjectionError:
                    pass
                raise

    def _apply_in_transaction(
        self, command: ProjectionCommand, *, timeout_seconds: float = 5.0
    ) -> str:
        if timeout_seconds <= 0:
            raise LadybugProjectionError("ladybug_query_timeout")
        with self._access_lock:
            if isinstance(command, NoGraphMutationCommand):
                return "noop"
            if isinstance(command, SourceExclusionProjectionCommand):
                rows = self._execute(
                    """
                    MATCH (event:SocialEvent {
                      event_id: $event_id, world_id: $world_id
                    })
                    RETURN count(event)
                    """,
                    {"world_id": command.world_id, "event_id": command.event_id},
                )
                removed = int(rows[0][0]) if rows else 0
                if removed:
                    self._execute(
                        """
                        MATCH (event:SocialEvent {
                          event_id: $event_id, world_id: $world_id
                        })
                        DETACH DELETE event
                        """,
                        {
                            "world_id": command.world_id,
                            "event_id": command.event_id,
                        },
                    )
                return "removed" if removed else "noop"
            if isinstance(command, SocialEventProjectionCommand):
                self._merge_event(command)
                return "applied"

            event = command.event
            self._merge_event(event)
            parameters = _event_parameters(event)
            existing_rows = self._execute(
                """
                MATCH (actor:WorldCharacter {
                  world_character_id: $actor_world_character_id,
                  world_id: $world_id
                })-[relationship:RELATES_TO]->
                (target:WorldCharacter {
                  world_character_id: $target_world_character_id,
                  world_id: $world_id
                })
                WHERE relationship.world_id = $world_id
                RETURN relationship.relationship_version
                LIMIT 1
                """,
                parameters,
            )
            existing_version = int(existing_rows[0][0] or 0) if existing_rows else 0
            if existing_version > command.relationship_version:
                return "stale_noop"
            parameters.update(
                {
                    "relationship_state_id": command.relationship_state_id,
                    "familiarity": command.familiarity,
                    "affinity": command.affinity,
                    "trust": command.trust,
                    "tension": command.tension,
                    "interaction_count": command.interaction_count,
                    "last_event_id": command.last_event_id,
                    "last_event_at": _datetime_text(command.last_event_at),
                    "updated_at": _datetime_text(command.updated_at),
                    "relationship_version": command.relationship_version,
                }
            )
            self._execute(
                """
                MATCH (actor:WorldCharacter {
                  world_character_id: $actor_world_character_id,
                  world_id: $world_id
                })
                MATCH (target:WorldCharacter {
                  world_character_id: $target_world_character_id,
                  world_id: $world_id
                })
                MATCH (event:SocialEvent {
                  event_id: $event_id, world_id: $world_id
                })
                MERGE (actor)-[relationship:RELATES_TO]->(target)
                SET relationship.world_id = $world_id,
                    relationship.relationship_state_id = $relationship_state_id,
                    relationship.familiarity = $familiarity,
                    relationship.affinity = $affinity,
                    relationship.trust = $trust,
                    relationship.tension = $tension,
                    relationship.interaction_count = $interaction_count,
                    relationship.last_event_id = $last_event_id,
                    relationship.last_event_at = $last_event_at,
                    relationship.updated_at = $updated_at,
                    relationship.relationship_version = $relationship_version
                MERGE (actor)-[grounded:RELATIONSHIP_GROUNDED_IN {
                  world_id: $world_id,
                  target_world_character_id: $target_world_character_id,
                  relationship_state_id: $relationship_state_id,
                  event_id: $event_id
                }]->(event)
                SET grounded.relationship_version = $relationship_version
                RETURN relationship.relationship_version
                """,
                parameters,
            )
            return "applied"

    def clear_world(self, world_id: str) -> None:
        with self._access_lock:
            for label in ("SocialEvent", "WorldCharacter", "World"):
                self._execute(
                    f"MATCH (node:{label} {{world_id: $world_id}}) DETACH DELETE node",
                    {"world_id": world_id},
                )

    def world_digest(self, world_id: str) -> dict[str, list[str]]:
        def entry(*values: object) -> str:
            return json.dumps(values, ensure_ascii=True, separators=(",", ":"))

        with self._access_lock:
            world_characters = self._execute(
                """
                MATCH (node:WorldCharacter {world_id: $world_id})
                RETURN DISTINCT node.world_character_id
                ORDER BY node.world_character_id
                """,
                {"world_id": world_id},
            )
            events = self._execute(
                """
                MATCH (event:SocialEvent {world_id: $world_id})
                RETURN DISTINCT event.event_id ORDER BY event.event_id
                """,
                {"world_id": world_id},
            )
            relationships = self._execute(
                """
                MATCH (actor:WorldCharacter {world_id: $world_id})
                      -[relationship:RELATES_TO]->
                      (target:WorldCharacter {world_id: $world_id})
                WHERE relationship.world_id = $world_id
                RETURN relationship.relationship_state_id,
                       actor.world_character_id,
                       target.world_character_id,
                       relationship.relationship_version,
                       relationship.familiarity,
                       relationship.affinity,
                       relationship.trust,
                       relationship.tension,
                       relationship.interaction_count
                ORDER BY relationship.relationship_state_id
                """,
                {"world_id": world_id},
            )
            evidence = self._execute(
                """
                MATCH (actor:WorldCharacter {world_id: $world_id})
                      -[grounded:RELATIONSHIP_GROUNDED_IN]->
                      (event:SocialEvent {world_id: $world_id})
                WHERE grounded.world_id = $world_id
                RETURN grounded.relationship_state_id,
                       actor.world_character_id,
                       grounded.target_world_character_id,
                       event.event_id,
                       grounded.relationship_version
                ORDER BY grounded.relationship_state_id,
                         actor.world_character_id,
                         grounded.target_world_character_id,
                         event.event_id,
                         grounded.relationship_version
                """,
                {"world_id": world_id},
            )
        return {
            "world_characters": [entry(row[0]) for row in world_characters],
            "events": [entry(row[0]) for row in events],
            "relationships": [entry(*row) for row in relationships],
            "evidence": [entry(*row) for row in evidence],
        }


__all__ = [
    "LADYBUG_PROJECTION_SCHEMA_VERSION",
    "LadybugProjectionError",
    "LadybugRelationshipProjection",
]
