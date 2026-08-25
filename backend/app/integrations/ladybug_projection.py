"""LadybugDB adapter for the replayable relationship graph projection.

SQLite remains the canonical event/outbox store. This adapter owns one
LadybugDB connection, accepts only validated relationship-domain commands, and
can be deleted and rebuilt without losing canonical user data.
"""

from __future__ import annotations

import ctypes
from collections import defaultdict, deque
from dataclasses import fields
from datetime import datetime
import gc
import hashlib
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
from app.domains.relationships.graph_read.repository import GraphQueryTemplate
from app.domains.relationships.projection.commands import (
    NoGraphMutationCommand,
    ProjectionCommand,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)


LADYBUG_PROJECTION_SCHEMA_VERSION = 1

_QUERY_RESULT_CONTRACT = {
    "direct_relationship": ("actor_id", "target_id", "relationship"),
    "shared_neighbors": ("world_character_id",),
    "shortest_path": ("world_character_ids", "oriented_edges", "hop_count"),
    "ranked_related": ("actor_id", "target_id", "relationship"),
    "relationship_evidence": (
        "event_id",
        "event_type",
        "occurred_at",
        "relationship_state_id",
        "relationship_version",
    ),
    "visualization": ("actor_id", "target_id", "relationship"),
}


def ladybug_projection_contract() -> dict[str, object]:
    """Return a stable contract fingerprint independent of graph contents."""

    def digest(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    command_types = (
        SocialEventProjectionCommand,
        RelationshipStateProjectionCommand,
        SourceExclusionProjectionCommand,
        NoGraphMutationCommand,
    )
    commands = {
        command.__name__: [
            {"name": field.name, "type": str(field.type)}
            for field in fields(command)
        ]
        for command in command_types
    }
    schema = [" ".join(statement.split()) for statement in _BOOTSTRAP_STATEMENTS]
    queries = {
        "templates": [template.value for template in GraphQueryTemplate],
        "results": _QUERY_RESULT_CONTRACT,
    }
    return {
        "projection_schema_version": LADYBUG_PROJECTION_SCHEMA_VERSION,
        "schema_digest": digest(schema),
        "projection_command_digest": digest(commands),
        "typed_query_digest": digest(queries),
        "parity_contract_version": 1,
        "minimum_ladybug_version": "0.19.1",
    }


class LadybugProjectionError(RelationshipProjectionBackendError):
    """Stable, sanitized LadybugDB error exposed to the projection worker."""


def inspect_ladybug_projection_schema_version(database_root: Path) -> int | None:
    """Read ProjectionMeta without changing or bootstrapping the graph."""

    root = database_root.resolve()
    if not (root / "relationships.lbdb").exists():
        return None
    writer_lock = _ExclusiveWriterLock(root / "relationships.writer.lock")
    path_alias = _WindowsAsciiPathAlias(root)
    database: Any | None = None
    connection: Any | None = None
    try:
        writer_lock.acquire()
        native_root = path_alias.open()
        database = lb.Database(str(native_root / "relationships.lbdb"))
        connection = lb.Connection(database)
        try:
            rows = _rows(
                connection.execute(
                    "MATCH (meta:ProjectionMeta {id: $id}) "
                    "RETURN meta.schema_version",
                    parameters={"id": "relationship_projection"},
                )
            )
        except Exception:
            return 0
        if not rows:
            return 0
        return int(rows[0][0])
    except LadybugProjectionError:
        raise
    except Exception:
        raise LadybugProjectionError("ladybug_unavailable") from None
    finally:
        connection = None
        database = None
        gc.collect()
        try:
            path_alias.close()
        finally:
            writer_lock.release()


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
            rows = self._execute(
                "MATCH (meta:ProjectionMeta {id: $id}) "
                "RETURN meta.schema_version, meta.adapter",
                {"id": "relationship_projection"},
            )
            if rows:
                version = int(rows[0][0])
                adapter = str(rows[0][1])
                if (
                    version != LADYBUG_PROJECTION_SCHEMA_VERSION
                    or adapter != "ladybug"
                ):
                    raise LadybugProjectionError(
                        "ladybug_schema_version_mismatch"
                    )
                return
            populated = 0
            for label in ("World", "WorldCharacter", "SocialEvent"):
                count_rows = self._execute(
                    f"MATCH (node:{label}) RETURN count(node)"
                )
                populated += int(count_rows[0][0])
            if populated:
                raise LadybugProjectionError("ladybug_schema_unversioned")
            self._execute(
                """
                CREATE (meta:ProjectionMeta {
                  id: $id,
                  schema_version: $schema_version,
                  adapter: $adapter
                })
                RETURN meta.schema_version
                """,
                {
                    "id": "relationship_projection",
                    "schema_version": LADYBUG_PROJECTION_SCHEMA_VERSION,
                    "adapter": "ladybug",
                },
            )

    def projection_schema_version(self) -> int:
        with self._access_lock:
            rows = self._execute(
                "MATCH (meta:ProjectionMeta {id: $id}) "
                "RETURN meta.schema_version",
                {"id": "relationship_projection"},
            )
            if len(rows) != 1:
                raise LadybugProjectionError("ladybug_schema_version_missing")
            return int(rows[0][0])

    def verify_connectivity(self) -> None:
        with self._access_lock:
            rows = self._execute("RETURN 1")
            if rows != [[1]]:
                raise LadybugProjectionError("ladybug_unavailable")

    @staticmethod
    def _relationship_payload(row: list[Any]) -> dict[str, Any]:
        return {
            "world_id": str(row[2]),
            "relationship_state_id": str(row[3]),
            "familiarity": int(row[4] or 0),
            "affinity": int(row[5] or 0),
            "trust": int(row[6] or 0),
            "tension": int(row[7] or 0),
            "interaction_count": int(row[8] or 0),
            "last_event_id": str(row[9]) if row[9] is not None else None,
            "last_event_at": str(row[10]) if row[10] is not None else None,
            "updated_at": str(row[11]) if row[11] is not None else None,
            "relationship_version": int(row[12] or 0),
        }

    def _relationship_rows(self, *, world_id: str) -> list[dict[str, Any]]:
        rows = self._execute(
            """
            MATCH (actor:WorldCharacter)-[relationship:RELATES_TO]->
                  (target:WorldCharacter)
            WHERE actor.world_id = $world_id
              AND target.world_id = $world_id
              AND relationship.world_id = $world_id
            RETURN actor.world_character_id,
                   target.world_character_id,
                   relationship.world_id,
                   relationship.relationship_state_id,
                   relationship.familiarity,
                   relationship.affinity,
                   relationship.trust,
                   relationship.tension,
                   relationship.interaction_count,
                   relationship.last_event_id,
                   relationship.last_event_at,
                   relationship.updated_at,
                   relationship.relationship_version
            """,
            {"world_id": world_id},
        )
        return [
            {
                "actor_id": str(row[0]),
                "target_id": str(row[1]),
                "relationship": self._relationship_payload(row),
            }
            for row in rows
        ]

    @staticmethod
    def _ordered_relationships(
        rows: list[dict[str, Any]], *, mode: str
    ) -> list[dict[str, Any]]:
        # Stable sorts reproduce the Neo4j ORDER BY clauses without relying on
        # provider-specific NULL ordering or relationship helper functions.
        rows = sorted(rows, key=lambda row: str(row["target_id"]))
        if mode == "positive":
            rows = sorted(
                rows,
                key=lambda row: (
                    -int(row["relationship"]["familiarity"]),
                    -int(row["relationship"]["affinity"]),
                    -int(row["relationship"]["trust"]),
                    int(row["relationship"]["tension"]),
                ),
            )
        elif mode == "tense":
            rows = sorted(
                rows,
                key=lambda row: str(row["relationship"]["updated_at"] or ""),
                reverse=True,
            )
            rows = sorted(
                rows,
                key=lambda row: (
                    -int(row["relationship"]["tension"]),
                    int(row["relationship"]["affinity"]),
                ),
            )
        else:
            rows = sorted(
                rows,
                key=lambda row: (
                    str(row["relationship"]["updated_at"] or ""),
                    int(row["relationship"]["interaction_count"]),
                ),
                reverse=True,
            )
        return rows

    @staticmethod
    def _adjacency(
        rows: list[dict[str, Any]], *, direction: str
    ) -> dict[str, list[tuple[str, dict[str, Any]]]]:
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for row in rows:
            actor = str(row["actor_id"])
            target = str(row["target_id"])
            if direction in {"outgoing", "either"}:
                adjacency[actor].append((target, row))
            if direction in {"incoming", "either"}:
                adjacency[target].append((actor, row))
        for values in adjacency.values():
            values.sort(
                key=lambda item: (
                    item[0],
                    str(item[1]["actor_id"]),
                    str(item[1]["target_id"]),
                    str(item[1]["relationship"]["relationship_state_id"]),
                )
            )
        return adjacency

    @classmethod
    def _shortest_path(
        cls,
        rows: list[dict[str, Any]],
        *,
        source_id: str,
        target_id: str,
        direction: str,
        max_hops: int,
    ) -> list[dict[str, Any]]:
        if source_id == target_id:
            return []
        adjacency = cls._adjacency(rows, direction=direction)
        queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque(
            [(source_id, [source_id], [])]
        )
        while queue:
            current, nodes, edges = queue.popleft()
            if len(edges) >= max_hops:
                continue
            for neighbor, edge in adjacency.get(current, []):
                if neighbor in nodes:
                    continue
                next_nodes = [*nodes, neighbor]
                next_edges = [*edges, edge]
                if neighbor == target_id:
                    return [
                        {
                            "world_character_ids": next_nodes,
                            "oriented_edges": next_edges,
                            "hop_count": len(next_edges),
                        }
                    ]
                queue.append((neighbor, next_nodes, next_edges))
        return []

    def run_template(
        self,
        template: GraphQueryTemplate,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute the bounded P7 read workload against LadybugDB.

        LadybugDB and Neo4j expose different Cypher helper functions.  The
        adapter therefore reads explicit typed relationship columns and keeps
        traversal/ranking limits in deterministic Python code while returning
        the exact provider-neutral row contract consumed by
        ``RelationshipGraphRepository``.
        """

        world_id = str(parameters["world_id"])
        source_id = str(parameters.get("source_id") or "")
        target_id = str(parameters.get("target_id") or "")
        with self._access_lock:
            relationships = self._relationship_rows(world_id=world_id)

            if template == GraphQueryTemplate.DIRECT_RELATIONSHIP:
                return [
                    row
                    for row in relationships
                    if row["actor_id"] == source_id
                    and row["target_id"] == target_id
                ][:1]

            if template in {
                GraphQueryTemplate.SHARED_NEIGHBORS_OUTGOING,
                GraphQueryTemplate.SHARED_NEIGHBORS_INCOMING,
                GraphQueryTemplate.SHARED_NEIGHBORS_EITHER,
            }:
                direction = {
                    GraphQueryTemplate.SHARED_NEIGHBORS_OUTGOING: "outgoing",
                    GraphQueryTemplate.SHARED_NEIGHBORS_INCOMING: "incoming",
                    GraphQueryTemplate.SHARED_NEIGHBORS_EITHER: "either",
                }[template]
                adjacency = self._adjacency(relationships, direction=direction)
                left = {value for value, _ in adjacency.get(source_id, [])}
                right = {value for value, _ in adjacency.get(target_id, [])}
                limit = int(parameters.get("limit") or 20)
                return [
                    {"world_character_id": value}
                    for value in sorted(left & right)[:limit]
                ]

            if template.value.startswith("shortest_path_"):
                _, _, direction, raw_hops = template.value.rsplit("_", 3)
                return self._shortest_path(
                    relationships,
                    source_id=source_id,
                    target_id=target_id,
                    direction=direction,
                    max_hops=int(raw_hops),
                )

            if template in {
                GraphQueryTemplate.RANK_POSITIVE,
                GraphQueryTemplate.RANK_TENSE,
                GraphQueryTemplate.RANK_RECENT,
            }:
                mode = {
                    GraphQueryTemplate.RANK_POSITIVE: "positive",
                    GraphQueryTemplate.RANK_TENSE: "tense",
                    GraphQueryTemplate.RANK_RECENT: "recent",
                }[template]
                limit = int(parameters.get("limit") or 20)
                outgoing = [
                    row for row in relationships if row["actor_id"] == source_id
                ]
                return self._ordered_relationships(outgoing, mode=mode)[:limit]

            if template == GraphQueryTemplate.RELATIONSHIP_EVIDENCE:
                rows = self._execute(
                    """
                    MATCH (actor:WorldCharacter)-[grounded:RELATIONSHIP_GROUNDED_IN]->
                          (event:SocialEvent)
                    WHERE actor.world_character_id = $source_id
                      AND actor.world_id = $world_id
                      AND event.world_id = $world_id
                      AND grounded.world_id = $world_id
                      AND grounded.target_world_character_id = $target_id
                    RETURN event.event_id,
                           event.event_type,
                           event.occurred_at,
                           grounded.relationship_state_id,
                           grounded.relationship_version
                    ORDER BY event.occurred_at DESC, event.event_id DESC
                    LIMIT $evidence_limit
                    """,
                    parameters,
                )
                return [
                    {
                        "event_id": str(row[0]),
                        "event_type": str(row[1]),
                        "occurred_at": str(row[2]),
                        "relationship_state_id": str(row[3]),
                        "relationship_version": int(row[4] or 0),
                    }
                    for row in rows
                ]

            if template in {
                GraphQueryTemplate.VISUALIZATION_1,
                GraphQueryTemplate.VISUALIZATION_2,
            }:
                depth = 1 if template == GraphQueryTemplate.VISUALIZATION_1 else 2
                edge_limit = int(parameters.get("edge_limit") or 40)
                adjacency = self._adjacency(relationships, direction="either")
                expanded = {source_id}
                frontier = {source_id}
                selected: dict[tuple[str, str, str], dict[str, Any]] = {}
                for _ in range(depth):
                    next_frontier: set[str] = set()
                    for node_id in sorted(frontier):
                        for neighbor, row in adjacency.get(node_id, []):
                            key = (
                                str(row["actor_id"]),
                                str(row["target_id"]),
                                str(
                                    row["relationship"]["relationship_state_id"]
                                ),
                            )
                            selected[key] = row
                            if neighbor not in expanded:
                                next_frontier.add(neighbor)
                    expanded.update(next_frontier)
                    frontier = next_frontier
                ordered = sorted(
                    selected.values(),
                    key=lambda row: (
                        str(row["actor_id"]),
                        str(row["target_id"]),
                    ),
                )
                ordered = sorted(
                    ordered,
                    key=lambda row: str(row["relationship"]["updated_at"] or ""),
                    reverse=True,
                )
                return ordered[:edge_limit]

        raise LadybugProjectionError("ladybug_query_template_unsupported")

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
    "inspect_ladybug_projection_schema_version",
    "ladybug_projection_contract",
]
