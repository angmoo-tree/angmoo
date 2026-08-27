"""Forward-only v2 to v3 explicit no-role normalization."""

from __future__ import annotations

from sqlalchemy import Connection, select, update
from sqlalchemy.orm import Session

from app.domains.routines.infrastructure.sqlalchemy_models import DailyActivityPlan
from app.domains.world_characters.infrastructure.sqlalchemy_models import WorldCharacter
from app.domains.world_characters.infrastructure.sqlalchemy_setup_models import (
    WorldActivityRepertoire,
    WorldCommunityProfile,
)
from app.domains.worlds.domain.reserved_roles import NO_SPECIFIC_ROLE_KEY
from app.domains.worlds.infrastructure import definition_repository
from app.domains.worlds.infrastructure.sqlalchemy_models import World
from app.domains.worlds.infrastructure.sqlalchemy_reserved_roles import (
    ensure_no_specific_role,
)


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


__all__ = ["upgrade_v2_to_v3"]
