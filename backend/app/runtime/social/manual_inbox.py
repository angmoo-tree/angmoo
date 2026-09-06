"""Bind canonical manual inbox policy to exact caller-Session World reads."""

from sqlalchemy.orm import Session
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership
from app.domains.social.service.manual_inbox import ManualInboxService
from app.domains.social.contracts.inbox import ManualInboxRuntimeError
from app.domains.social.utils.manual_inbox import (
    source_id,
    candidate_id,
    is_manual_inbox_source,
)


class RuntimeManualInboxReferences:
    def get_world_character(
        self, db: Session, world_character_id: str
    ) -> WorldCharacter | None:
        return db.get(WorldCharacter, world_character_id)

    def get_membership(self, db: Session, membership_id: str) -> WorldMembership | None:
        return db.get(WorldMembership, membership_id)


manual_inbox_service = ManualInboxService(RuntimeManualInboxReferences())
candidates = manual_inbox_service.candidates
claim = manual_inbox_service.claim
claimed_observation_post_id = manual_inbox_service.claimed_observation_post_id
release_claims = manual_inbox_service.release_claims
consume_claims = manual_inbox_service.consume_claims


__all__ = ['ManualInboxRuntimeError', 'candidate_id', 'candidates', 'claimed_observation_post_id', 'claim', 'consume_claims', 'is_manual_inbox_source', 'release_claims', 'source_id']
