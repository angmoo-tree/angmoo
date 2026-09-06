"""Original cross-owner SQL reads used by canonical Chat preflight."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import InstallationIdentity
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import World, WorldMembership


def installation(
    session: Session, command: RetrievalPreflightCommand
) -> InstallationIdentity | None:
    return session.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)


def world(session: Session, command: RetrievalPreflightCommand) -> World | None:
    return session.scalar(
        select(World)
        .join(
            WorldMembership,
            (WorldMembership.world_id == World.id)
            & (WorldMembership.user_id == command.owner_id),
        )
        .where(
            World.id == command.world_id,
            World.owner_user_id == command.owner_id,
            World.status != "archived",
            WorldMembership.role == "owner",
            WorldMembership.status == "active",
        )
    )


def memory_enabled(session: Session, command: RetrievalPreflightCommand) -> bool | None:
    return session.scalar(
        select(MemoryScopeSettingModel.enabled).where(
            MemoryScopeSettingModel.owner_id == command.owner_id,
            MemoryScopeSettingModel.world_id == command.world_id,
            MemoryScopeSettingModel.subject_world_character_id
            == command.responding_world_character_id,
        )
    )


def entity_mentions(
    session: Session, *, world_id: str, normalized: str
) -> list[tuple[WorldCharacter, Character, WorldMembership]]:
    return session.execute(
        select(WorldCharacter, Character, WorldMembership)
        .join(Character, Character.id == WorldCharacter.character_id)
        .join(
            WorldMembership,
            (WorldMembership.id == WorldCharacter.membership_id)
            & (WorldMembership.world_id == WorldCharacter.world_id),
        )
        .where(
            WorldCharacter.world_id == world_id,
            WorldCharacter.status == "active",
            WorldMembership.status == "active",
            Character.deleted_at.is_(None),
            Character.moderation_status == "active",
            or_(
                func.lower(Character.name) == normalized,
                func.lower(Character.handle) == normalized,
            ),
        )
        .order_by(WorldCharacter.id)
        .limit(5)
    ).all()


def active_world_character(
    session: Session, *, world_id: str, world_character_id: str
) -> tuple[WorldCharacter, Character, WorldMembership] | None:
    return session.execute(
        select(WorldCharacter, Character, WorldMembership)
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
