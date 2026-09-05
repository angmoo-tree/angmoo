"""Canonical retrieval admission and Unicode entity eligibility policies."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.chat.contracts.context import WorldCharacterBlockQuery
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.retrieval_policy import (
    CanonicalRetrievalScope,
    RetrievalEntityCandidate,
    RetrievalEntityResolution,
    RetrievalPreflightCommand,
)
from app.domains.chat.contracts.retrieval_reads import RetrievalPolicyReads
from app.domains.chat.repository import response_requests as request_repository


class RetrievalPolicyResolver:
    def __init__(
        self,
        session: Session,
        reads: RetrievalPolicyReads,
        blocked_query: WorldCharacterBlockQuery,
    ) -> None:
        self._session = session
        self.reads = reads
        self._blocked_query = blocked_query

    def load_scope(self, command: RetrievalPreflightCommand) -> CanonicalRetrievalScope:
        installation = self.reads.installation(self._session, command)
        if (
            installation is None
            or installation.bootstrap_state != "claimed"
            or installation.owner_user_id != command.owner_id
        ):
            raise RetrievalContractError("retrieval_preflight_local_owner_forbidden")
        world = self.reads.world(self._session, command)
        if world is None:
            raise RetrievalContractError("retrieval_preflight_world_forbidden")
        thread = request_repository.get_preflight_thread(self._session, command)
        if thread is None:
            raise RetrievalContractError("retrieval_preflight_thread_scope_invalid")
        requester = self.reads.active_world_character(
            self._session,
            world_id=command.world_id,
            world_character_id=command.requester_world_character_id,
        )
        responding = self.reads.active_world_character(
            self._session,
            world_id=command.world_id,
            world_character_id=command.responding_world_character_id,
        )
        if requester is None or responding is None:
            raise RetrievalContractError("retrieval_preflight_character_inactive")
        requester_world_character, requester_character, requester_membership = requester
        _responding_world_character, responding_character, _responding_membership = (
            responding
        )
        if (
            requester_world_character.control_mode != "owner_controlled"
            or requester_world_character.owner_user_id != command.owner_id
            or requester_character.owner_id != command.owner_id
            or (requester_membership.user_id != command.owner_id)
            or (requester_membership.role != "owner")
        ):
            raise RetrievalContractError("retrieval_preflight_requester_forbidden")
        if self._pair_is_blocked(
            command.world_id,
            command.requester_world_character_id,
            command.responding_world_character_id,
        ):
            raise RetrievalContractError("retrieval_preflight_pair_blocked")
        memory_enabled = bool(self.reads.memory_enabled(self._session, command))
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
        self, scope: CanonicalRetrievalScope, mentions: tuple[tuple[str, str], ...]
    ) -> tuple[RetrievalEntityResolution, ...]:
        results: list[RetrievalEntityResolution] = []
        for ref, mention in mentions:
            normalized = mention.strip().removeprefix("@").casefold()
            rows = self.reads.entity_mentions(
                self._session, world_id=scope.world_id, normalized=normalized
            )
            candidates: list[RetrievalEntityCandidate] = []
            for world_character, character, membership in rows:
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
                        active=world_character.status == "active"
                        and membership.status == "active",
                        blocked=blocked,
                        visible=character.deleted_at is None
                        and character.moderation_status == "active",
                        observable=not blocked,
                    )
                )
            results.append(
                RetrievalEntityResolution(ref=ref, candidates=tuple(candidates))
            )
        return tuple(results)

    def _pair_is_blocked(self, world_id: str, first_id: str, second_id: str) -> bool:
        return self._blocked_query(
            self._session,
            world_id=world_id,
            first_world_character_id=first_id,
            second_world_character_id=second_id,
        )
