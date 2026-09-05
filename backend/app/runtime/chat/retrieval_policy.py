"""SQLAlchemy adapter for P8-L-K canonical retrieval scope resolution."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.chat.domain.retrieval_intent import RetrievalContractError
from app.domains.chat.infrastructure.sqlalchemy_models import MessageThread
from app.domains.chat.ports.retrieval_policy import (
    CanonicalRetrievalScope,
    RetrievalEntityCandidate,
    RetrievalEntityResolution,
    RetrievalPreflightCommand,
)
from app.domains.identity.public import (
    InstallationIdentity,
    LOCAL_INSTALLATION_KEY,
)
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryScopeSettingModel,
)
from app.domains.world_characters.infrastructure.sqlalchemy_models import (
    WorldCharacter,
)
from app.domains.worlds.models import World, WorldMembership
from app.runtime.relationships.sqlalchemy_social_event import (
    world_character_pair_is_blocked,
)


class SqlAlchemyRetrievalPolicyResolver:
    """Read canonical facts; never accepts an LLM-provided identifier."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_scope(self, command: RetrievalPreflightCommand) -> CanonicalRetrievalScope:
        installation = self._session.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
        if (
            installation is None
            or installation.bootstrap_state != "claimed"
            or installation.owner_user_id != command.owner_id
        ):
            raise RetrievalContractError("retrieval_preflight_local_owner_forbidden")

        world = self._session.scalar(
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
        if world is None:
            raise RetrievalContractError("retrieval_preflight_world_forbidden")

        thread = self._session.scalar(
            select(MessageThread).where(
                MessageThread.id == command.thread_id,
                MessageThread.requester_id == command.owner_id,
                MessageThread.world_id == command.world_id,
                MessageThread.requester_world_character_id
                == command.requester_world_character_id,
                MessageThread.responding_world_character_id
                == command.responding_world_character_id,
                MessageThread.world_scope_status == "resolved",
                MessageThread.deleted_at.is_(None),
            )
        )
        if thread is None:
            raise RetrievalContractError("retrieval_preflight_thread_scope_invalid")

        requester = self._active_world_character(
            world_id=command.world_id,
            world_character_id=command.requester_world_character_id,
        )
        responding = self._active_world_character(
            world_id=command.world_id,
            world_character_id=command.responding_world_character_id,
        )
        if requester is None or responding is None:
            raise RetrievalContractError("retrieval_preflight_character_inactive")
        requester_world_character, requester_character, requester_membership = requester
        _responding_world_character, responding_character, _responding_membership = responding
        if (
            requester_world_character.control_mode != "owner_controlled"
            or requester_world_character.owner_user_id != command.owner_id
            or requester_character.owner_id != command.owner_id
            or requester_membership.user_id != command.owner_id
            or requester_membership.role != "owner"
        ):
            raise RetrievalContractError("retrieval_preflight_requester_forbidden")
        if self._pair_is_blocked(
            command.world_id,
            command.requester_world_character_id,
            command.responding_world_character_id,
        ):
            raise RetrievalContractError("retrieval_preflight_pair_blocked")

        memory_enabled = bool(
            self._session.scalar(
                select(MemoryScopeSettingModel.enabled).where(
                    MemoryScopeSettingModel.owner_id == command.owner_id,
                    MemoryScopeSettingModel.world_id == command.world_id,
                    MemoryScopeSettingModel.subject_world_character_id
                    == command.responding_world_character_id,
                )
            )
        )
        return CanonicalRetrievalScope(
            request_id=command.request_id,
            owner_id=command.owner_id,
            world_id=command.world_id,
            thread_id=command.thread_id,
            requester_world_character_id=command.requester_world_character_id,
            responding_world_character_id=command.responding_world_character_id,
            world_timezone=world.timezone,
            world_language=world.language,
            responding_character_name=responding_character.name,
            memory_enabled=memory_enabled,
        )

    def resolve_entity_mentions(
        self,
        scope: CanonicalRetrievalScope,
        mentions: tuple[tuple[str, str], ...],
    ) -> tuple[RetrievalEntityResolution, ...]:
        results: list[RetrievalEntityResolution] = []
        for ref, mention in mentions:
            normalized = mention.strip().removeprefix("@").casefold()
            rows = self._session.execute(
                select(WorldCharacter, Character, WorldMembership)
                .join(Character, Character.id == WorldCharacter.character_id)
                .join(
                    WorldMembership,
                    (WorldMembership.id == WorldCharacter.membership_id)
                    & (WorldMembership.world_id == WorldCharacter.world_id),
                )
                .where(
                    WorldCharacter.world_id == scope.world_id,
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
            candidates: list[RetrievalEntityCandidate] = []
            for world_character, character, membership in rows:
                # Database collation differs by runtime, so exact Unicode
                # casefolding is rechecked in code before accepting identity.
                if normalized not in {
                    character.name.strip().casefold(),
                    character.handle.strip().removeprefix("@").casefold(),
                }:
                    continue
                blocked = self._pair_is_blocked(
                    scope.world_id,
                    scope.responding_world_character_id,
                    world_character.id,
                )
                candidates.append(
                    RetrievalEntityCandidate(
                        world_character_id=world_character.id,
                        display_name=character.name,
                        handle=character.handle,
                        active=(
                            world_character.status == "active"
                            and membership.status == "active"
                        ),
                        blocked=blocked,
                        visible=character.deleted_at is None
                        and character.moderation_status == "active",
                        # Identity clarification is observable only inside the
                        # same active World and across an unblocked pair. Source
                        # evidence still receives its own H/I revalidation.
                        observable=not blocked,
                    )
                )
            results.append(
                RetrievalEntityResolution(ref=ref, candidates=tuple(candidates))
            )
        return tuple(results)

    def _active_world_character(
        self,
        *,
        world_id: str,
        world_character_id: str,
    ) -> tuple[WorldCharacter, Character, WorldMembership] | None:
        return self._session.execute(
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

    def _pair_is_blocked(self, world_id: str, first_id: str, second_id: str) -> bool:
        return world_character_pair_is_blocked(
            self._session,
            world_id=world_id,
            first_world_character_id=first_id,
            second_world_character_id=second_id,
        )


__all__ = ["SqlAlchemyRetrievalPolicyResolver"]
