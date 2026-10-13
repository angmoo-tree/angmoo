"""Original cross-owner SQL reads used by canonical Chat preflight."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.service.environment import snapshot
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.characters.service.import_configuration import ImportProfile
from app.domains.characters.service.profile import normalize_character_handle
from app.domains.chat.contracts.retrieval_reads import NamedEntityRead
from app.domains.chat.contracts.retrieval_policy import RetrievalEntityCandidate
from app.domains.worlds.models import World, WorldMembership


def environment(session: Session, command: RetrievalPreflightCommand):
    return command.environment or snapshot(session, command.owner_id)


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


def named_entity_mentions(session: Session, *, world_id: str, mention: str,
    frozen_ids: tuple[str, ...] = ()) -> NamedEntityRead:
    """Bounded canonical World name projection; never load the full roster/profile."""
    display = WorldCharacterConfiguration.profile["display_name"].as_string()
    handle = WorldCharacterConfiguration.profile["handle"].as_string()
    predicates = [display == mention]
    if mention.startswith("@"):
        try:
            predicates.append(handle == normalize_character_handle(mention))
        except ValueError:
            pass  # An invalid handle cannot become a fuzzy display-name lookup.
    if frozen_ids:
        predicates.append(WorldCharacter.id.in_(frozen_ids))
    statement = (select(WorldCharacter.id, display, handle)
        .join(Character, Character.id == WorldCharacter.character_id)
        .join(WorldMembership, (WorldMembership.id == WorldCharacter.membership_id)
            & (WorldMembership.world_id == WorldCharacter.world_id))
        .outerjoin(WorldCharacterConfiguration, WorldCharacterConfiguration.world_character_id == WorldCharacter.id)
        .where(WorldCharacter.world_id == world_id, WorldCharacter.status == "active",
            WorldMembership.status == "active", Character.deleted_at.is_(None),
            Character.moderation_status == "active", or_(*predicates))
        .order_by(WorldCharacter.id).limit(6))
    rows = session.execute(statement).all()
    complete = len(rows) <= 5 and set(frozen_ids) <= {row[0] for row in rows}
    candidates = []
    for identifier, name, canonical_handle in rows[:5]:
        try:
            profile = ImportProfile.model_validate({"display_name": name, "handle": canonical_handle})
        except ValueError:
            complete = False
            continue
        candidates.append(RetrievalEntityCandidate(identifier, profile.display_name, profile.handle,
            active=True, blocked=False, visible=True, observable=True))
    return NamedEntityRead(tuple(candidates), complete)


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
