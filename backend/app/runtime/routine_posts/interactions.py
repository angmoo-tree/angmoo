"""Compose canonical successful-event and manual-reply interaction sources."""

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.social.models.posts import Post
from app.domains.social.contracts.inbox import ManualInboxInteractionCandidate
from app.domains.social.repository import event_evidence, interaction_context
from app.domains.relationships.service.routine_interactions import (
    CanonicalRoutineInteractionService,
)
from app.runtime.social.manual_inbox import (
    RuntimeManualInboxReferences,
    manual_inbox_service,
)


class RuntimeRoutineInteractionReferences(RuntimeManualInboxReferences):
    def get_post(self, db: Session, post_id: str) -> Post | None:
        return event_evidence.get_post(db, post_id)

    def pair_blocked(
        self, db: Session, *, world_id: str, first_id: str, second_id: str
    ) -> bool:
        return interaction_context._blocked(
            db, world_id=world_id, first_id=first_id, second_id=second_id
        )

    def manual_inbox_candidates(
        self,
        db: Session,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[ManualInboxInteractionCandidate]:
        return manual_inbox_service.candidates(
            db,
            world_id=world_id,
            consumer_world_character_id=consumer_world_character_id,
            episode_id=episode_id,
            after=after,
            before=before,
        )


class CanonicalRoutineInteractionSource(CanonicalRoutineInteractionService):
    def __init__(self) -> None:
        super().__init__(RuntimeRoutineInteractionReferences())


def canonical_interaction_source() -> object:
    """Build the canonical successful-social-event adapter."""
    return CanonicalRoutineInteractionSource()
