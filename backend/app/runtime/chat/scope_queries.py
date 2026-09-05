"""Joined canonical reads for Chat, using the caller's Session and lock scope.

These queries preserve the existing filter and lock differences. Chat services
interpret nullable results and cardinality; this module never commits or denies.
"""

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.chat.repository.threads import _is_postgresql_session
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import InstallationIdentity
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import World, WorldMembership


def owner_controlled_world_characters(
    db: Session, owner_id: str, world_id: str, *, lock_scope: bool = False
) -> list[WorldCharacter]:
    statement = (
        select(WorldCharacter)
        .join(Character, Character.id == WorldCharacter.character_id)
        .join(
            WorldMembership,
            (WorldMembership.id == WorldCharacter.membership_id)
            & (WorldMembership.world_id == WorldCharacter.world_id),
        )
        .where(
            WorldCharacter.world_id == world_id,
            WorldCharacter.owner_user_id == owner_id,
            WorldCharacter.control_mode == "owner_controlled",
            WorldCharacter.status == "active",
            Character.owner_id == owner_id,
            WorldMembership.status == "active",
            WorldMembership.user_id == owner_id,
            WorldMembership.role == "owner",
            Character.deleted_at.is_(None),
            Character.moderation_status == "active",
        )
        .order_by(WorldCharacter.id)
        .limit(2)
    )
    if lock_scope and _is_postgresql_session(db):
        statement = statement.with_for_update()
    return list(db.scalars(statement))


def local_installation(
    db: Session, *, lock_scope: bool = False
) -> InstallationIdentity | None:
    if lock_scope and _is_postgresql_session(db):
        installation = db.scalar(
            select(InstallationIdentity)
            .where(InstallationIdentity.singleton_key == LOCAL_INSTALLATION_KEY)
            .with_for_update()
        )
    else:
        installation = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
    return installation


def owned_world_id(
    db: Session, owner_id: str, world_id: str, *, lock_scope: bool = False
) -> str | None:
    owned_world_statement = (
        select(World.id)
        .join(
            WorldMembership,
            (WorldMembership.world_id == World.id)
            & (WorldMembership.user_id == owner_id),
        )
        .where(
            World.id == world_id,
            World.owner_user_id == owner_id,
            World.status != "archived",
            WorldMembership.role == "owner",
            WorldMembership.status == "active",
        )
    )
    if lock_scope and _is_postgresql_session(db):
        owned_world_statement = owned_world_statement.with_for_update()
    owned_world = db.scalar(owned_world_statement)
    return owned_world


def responding_world_character(
    db: Session, world_id: str, world_character_id: str
) -> tuple[WorldCharacter, Character] | None:
    row = db.execute(
        select(WorldCharacter, Character)
        .join(Character, Character.id == WorldCharacter.character_id)
        .join(
            WorldMembership,
            (WorldMembership.id == WorldCharacter.membership_id)
            & (WorldMembership.world_id == WorldCharacter.world_id),
        )
        .where(
            WorldCharacter.id == world_character_id,
            WorldCharacter.world_id == world_id,
            WorldCharacter.status == "active",
            WorldMembership.status == "active",
            Character.deleted_at.is_(None),
            Character.moderation_status == "active",
        )
    ).one_or_none()
    return row


def world_chat_role(
    db: Session,
    world_character_id: str,
    *,
    world_id: str,
    expected_owner_id: str | None = None,
    lock_scope: bool = False,
) -> tuple[WorldCharacter, Character] | None:
    statement = (
        select(WorldCharacter, Character)
        .join(Character, Character.id == WorldCharacter.character_id)
        .join(
            WorldMembership,
            (WorldMembership.id == WorldCharacter.membership_id)
            & (WorldMembership.world_id == WorldCharacter.world_id),
        )
        .where(
            WorldCharacter.id == world_character_id,
            WorldCharacter.world_id == world_id,
            WorldCharacter.status == "active",
            WorldMembership.status == "active",
            Character.deleted_at.is_(None),
            Character.moderation_status == "active",
        )
    )
    if expected_owner_id is not None:
        statement = statement.where(
            WorldCharacter.control_mode == "owner_controlled",
            WorldCharacter.owner_user_id == expected_owner_id,
            Character.owner_id == expected_owner_id,
            WorldMembership.user_id == expected_owner_id,
            WorldMembership.role == "owner",
        )
    if lock_scope and _is_postgresql_session(db):
        statement = statement.with_for_update()
    row = db.execute(statement).one_or_none()
    return row


def claimed_local_installation_exists(db: Session) -> bool:
    if not inspect(db.get_bind()).has_table(InstallationIdentity.__tablename__):
        return False
    installation = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
    return bool(installation and installation.bootstrap_state == "claimed")
