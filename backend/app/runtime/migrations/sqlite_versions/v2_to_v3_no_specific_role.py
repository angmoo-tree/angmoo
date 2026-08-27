"""Forward-only v2 to v3 explicit no-role normalization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from sqlalchemy import Connection, select, update
from sqlalchemy.orm import Session

from app.domains.routines.infrastructure.sqlalchemy_models import DailyActivityPlan
from app.domains.world_characters.infrastructure.sqlalchemy_models import WorldCharacter
from app.domains.world_characters.infrastructure.sqlalchemy_setup_models import (
    WorldActivityRepertoire,
    WorldCommunityProfile,
)
from app.domains.worlds.domain.reserved_roles import NO_SPECIFIC_ROLE_KEY
from app.domains.worlds.domain.reserved_roles import (
    NO_SPECIFIC_ROLE_DESCRIPTION,
    NO_SPECIFIC_ROLE_NAME,
)
from app.domains.worlds.infrastructure import definition_repository
from app.domains.worlds.infrastructure.sqlalchemy_models import World
from app.domains.worlds.infrastructure.sqlalchemy_reserved_roles import (
    ensure_no_specific_role,
)
from app.runtime.migrations.sqlite_versions.contracts import (
    SqliteMigrationDeltaError,
)


MUTABLE_IDENTITY_TABLES = frozenset(
    {
        "daily_activity_plans",
        "world_activity_repertoires",
        "world_characters",
        "world_community_profiles",
        "world_roles",
        "worlds",
    }
)


@dataclass(frozen=True)
class V2ToV3DeltaSnapshot:
    affected_world_ids: tuple[str, ...]
    target_world_character_ids: tuple[str, ...]
    tables: dict[str, dict[str, dict[str, Any]]]


def _table_rows(connection: Connection, table: str) -> dict[str, dict[str, Any]]:
    quoted = '"' + table.replace('"', '""') + '"'
    rows = connection.exec_driver_sql(f"SELECT * FROM {quoted}").mappings()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = dict(row)
        key = str(payload.get("id", payload.get("character_id", "")))
        if not key or key in result:
            raise SqliteMigrationDeltaError(
                "sqlite_migration_expected_delta_mismatch"
            )
        result[key] = payload
    return result


def _canonical_reserved_role(row: dict[str, Any]) -> bool:
    def json_value(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    return (
        row["role_key"] == NO_SPECIFIC_ROLE_KEY
        and row["name"] == NO_SPECIFIC_ROLE_NAME
        and row["description"] == NO_SPECIFIC_ROLE_DESCRIPTION
        and json_value(row["responsibilities"]) == []
        and json_value(row["allowed_activity_scope"]) == []
        and bool(row["autonomous_allowed"]) is True
    )


def _same_except(
    before: dict[str, Any],
    after: dict[str, Any],
    allowed: set[str],
) -> bool:
    return {
        key: value for key, value in before.items() if key not in allowed
    } == {key: value for key, value in after.items() if key not in allowed}


def _delta_mismatch() -> None:
    raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def capture_v2_to_v3_delta(connection: Connection) -> V2ToV3DeltaSnapshot:
    tables = {
        table: _table_rows(connection, table)
        for table in sorted(MUTABLE_IDENTITY_TABLES)
    }
    world_characters = tables["world_characters"]
    targets = tuple(
        sorted(
            row_id
            for row_id, row in world_characters.items()
            if row["control_mode"] == "autonomous" and row["role_key"] is None
        )
    )
    affected_worlds = tuple(
        sorted({str(world_characters[row_id]["world_id"]) for row_id in targets})
    )
    worlds = tables["worlds"]
    roles = tables["world_roles"]
    for world_id in affected_worlds:
        if world_id not in worlds:
            raise SqliteMigrationDeltaError("sqlite_migration_roleless_world_missing")
        reserved = [
            row
            for row in roles.values()
            if row["world_id"] == world_id
            and row["role_key"] == NO_SPECIFIC_ROLE_KEY
        ]
        if len(reserved) > 1 or (
            reserved and not _canonical_reserved_role(reserved[0])
        ):
            raise SqliteMigrationDeltaError(
                "sqlite_migration_reserved_role_conflict"
            )
    return V2ToV3DeltaSnapshot(
        affected_world_ids=affected_worlds,
        target_world_character_ids=targets,
        tables=tables,
    )


def verify_v2_to_v3_delta(
    connection: Connection,
    snapshot: V2ToV3DeltaSnapshot,
) -> None:
    after = {
        table: _table_rows(connection, table)
        for table in sorted(MUTABLE_IDENTITY_TABLES)
    }
    before = snapshot.tables
    affected = set(snapshot.affected_world_ids)
    targets = set(snapshot.target_world_character_ids)

    for table in (
        "daily_activity_plans",
        "world_activity_repertoires",
        "world_characters",
        "world_community_profiles",
        "worlds",
    ):
        if set(before[table]) != set(after[table]):
            _delta_mismatch()

    before_roles = before["world_roles"]
    after_roles = after["world_roles"]
    missing_reserved = 0
    for world_id in affected:
        old_reserved = [
            row
            for row in before_roles.values()
            if row["world_id"] == world_id
            and row["role_key"] == NO_SPECIFIC_ROLE_KEY
        ]
        new_reserved = [
            row
            for row in after_roles.values()
            if row["world_id"] == world_id
            and row["role_key"] == NO_SPECIFIC_ROLE_KEY
        ]
        if len(new_reserved) != 1 or not _canonical_reserved_role(new_reserved[0]):
            _delta_mismatch()
        if not old_reserved:
            missing_reserved += 1
            if int(new_reserved[0]["version"]) != 1 or new_reserved[0]["status"] != "enabled":
                _delta_mismatch()
        else:
            old = old_reserved[0]
            new = new_reserved[0]
            if old["id"] != new["id"] or not _same_except(
                old, new, {"status", "version", "updated_at"}
            ):
                _delta_mismatch()
            expected_version = int(old["version"]) + (
                1 if old["status"] != "enabled" else 0
            )
            if new["status"] != "enabled" or int(new["version"]) != expected_version:
                _delta_mismatch()

    if len(after_roles) != len(before_roles) + missing_reserved:
        _delta_mismatch()
    for role_id, old in before_roles.items():
        if (
            old["world_id"] in affected
            and old["role_key"] == NO_SPECIFIC_ROLE_KEY
        ):
            continue
        if after_roles.get(role_id) != old:
            _delta_mismatch()

    old_worlds = before["worlds"]
    new_worlds = after["worlds"]
    for world_id, old in old_worlds.items():
        new = new_worlds[world_id]
        if world_id not in affected:
            if new != old:
                _delta_mismatch()
            continue
        if not _same_except(
            old,
            new,
            {
                "contract_hash",
                "definition_version",
                "row_version",
                "readiness_status",
                "updated_at",
            },
        ):
            _delta_mismatch()
        session = Session(bind=connection, join_transaction_mode="rollback_only")
        try:
            world = session.get(World, world_id)
            if world is None:
                _delta_mismatch()
            recomputed = definition_repository.world_contract_hash(session, world)
        finally:
            session.close()
        if new["contract_hash"] != recomputed:
            _delta_mismatch()
        changed = new["contract_hash"] != old["contract_hash"]
        if int(new["definition_version"]) != int(old["definition_version"]) + int(changed):
            _delta_mismatch()
        if int(new["row_version"]) != int(old["row_version"]) + int(changed):
            _delta_mismatch()

    old_characters = before["world_characters"]
    new_characters = after["world_characters"]
    for row_id, old in old_characters.items():
        new = new_characters[row_id]
        if not _same_except(
            old,
            new,
            {"role_key", "version", "world_contract_hash", "updated_at"},
        ):
            _delta_mismatch()
        if row_id in targets:
            if (
                new["role_key"] != NO_SPECIFIC_ROLE_KEY
                or int(new["version"]) != int(old["version"]) + 1
            ):
                _delta_mismatch()
        elif new["role_key"] != old["role_key"] or new["version"] != old["version"]:
            _delta_mismatch()
        world_id = str(old["world_id"])
        expected_hash = old["world_contract_hash"]
        if (
            world_id in affected
            and old["world_contract_hash"] == old_worlds[world_id]["contract_hash"]
        ):
            expected_hash = new_worlds[world_id]["contract_hash"]
        if new["world_contract_hash"] != expected_hash:
            _delta_mismatch()

    world_by_character = {
        row_id: str(row["world_id"]) for row_id, row in old_characters.items()
    }
    for table, hash_column in (
        ("world_community_profiles", "world_contract_hash"),
        ("world_activity_repertoires", "world_contract_hash"),
        ("daily_activity_plans", "world_definition_hash"),
    ):
        for row_id, old in before[table].items():
            new = after[table][row_id]
            if not _same_except(old, new, {hash_column, "updated_at"}):
                _delta_mismatch()
            world_character_id = str(old["world_character_id"])
            world_id = world_by_character.get(world_character_id)
            expected_hash = old[hash_column]
            if (
                world_id in affected
                and old[hash_column] == old_worlds[world_id]["contract_hash"]
            ):
                expected_hash = new_worlds[world_id]["contract_hash"]
            if new[hash_column] != expected_hash:
                _delta_mismatch()


def upgrade_v2_to_v3(connection: Connection) -> None:
    session = Session(bind=connection, join_transaction_mode="rollback_only")
    try:
        world_ids = tuple(
            session.scalars(
                select(WorldCharacter.world_id)
                .where(
                    WorldCharacter.control_mode == "autonomous",
                    WorldCharacter.role_key.is_(None),
                )
                .distinct()
                .order_by(WorldCharacter.world_id)
            )
        )
        for world_id in world_ids:
            world = session.get(World, world_id)
            if world is None:
                raise ValueError("roleless_world_missing")
            old_world_hash = world.contract_hash
            ensure_no_specific_role(session, world_id=world_id)
            roleless_character_ids = tuple(
                session.scalars(
                    select(WorldCharacter.id).where(
                        WorldCharacter.world_id == world_id,
                        WorldCharacter.control_mode == "autonomous",
                        WorldCharacter.role_key.is_(None),
                    )
                )
            )
            session.execute(
                update(WorldCharacter)
                .where(WorldCharacter.id.in_(roleless_character_ids))
                .values(
                    role_key=NO_SPECIFIC_ROLE_KEY,
                    version=WorldCharacter.version + 1,
                )
            )
            session.flush()
            world_character_ids = tuple(
                session.scalars(
                    select(WorldCharacter.id).where(
                        WorldCharacter.world_id == world_id
                    )
                )
            )
            new_world_hash = definition_repository.world_contract_hash(session, world)
            if new_world_hash != old_world_hash:
                world.contract_hash = new_world_hash
                world.definition_version += 1
                world.row_version += 1
                definition_repository.refresh_world_contract(session, world)
                session.execute(
                    update(WorldCharacter)
                    .where(
                        WorldCharacter.id.in_(world_character_ids),
                        WorldCharacter.world_contract_hash == old_world_hash,
                    )
                    .values(world_contract_hash=new_world_hash)
                )
                session.execute(
                    update(WorldCommunityProfile)
                    .where(
                        WorldCommunityProfile.world_character_id.in_(
                            world_character_ids
                        ),
                        WorldCommunityProfile.world_contract_hash == old_world_hash,
                    )
                    .values(world_contract_hash=new_world_hash)
                )
                session.execute(
                    update(WorldActivityRepertoire)
                    .where(
                        WorldActivityRepertoire.world_character_id.in_(
                            world_character_ids
                        ),
                        WorldActivityRepertoire.world_contract_hash == old_world_hash,
                    )
                    .values(world_contract_hash=new_world_hash)
                )
                session.execute(
                    update(DailyActivityPlan)
                    .where(
                        DailyActivityPlan.world_character_id.in_(
                            world_character_ids
                        ),
                        DailyActivityPlan.world_definition_hash == old_world_hash,
                    )
                    .values(world_definition_hash=new_world_hash)
                )
        session.flush()
    finally:
        session.close()


__all__ = [
    "MUTABLE_IDENTITY_TABLES",
    "V2ToV3DeltaSnapshot",
    "capture_v2_to_v3_delta",
    "upgrade_v2_to_v3",
    "verify_v2_to_v3_delta",
]
