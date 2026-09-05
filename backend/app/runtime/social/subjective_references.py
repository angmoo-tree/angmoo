"""Concrete World, actor and successful evidence reads at their original positions."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.relationships.models.social import SocialEventEvidence
from app.domains.worlds.models import World
from app.domains.world_characters.models import WorldCharacter
from app.domains.social.contracts.subjective_persistence import (
    SubjectiveWorld,
    SubjectiveEvidence,
)
from app.domains.social.contracts.source_writes import SourceWorldCharacter


class RuntimeSubjectiveReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_world(self, world_id: str) -> SubjectiveWorld | None:
        return self.db.get(World, world_id)

    def get_actor(self, actor_id: str) -> SourceWorldCharacter | None:
        return self.db.get(WorldCharacter, actor_id)

    def get_evidence(
        self, *, event_id: str, execution_id: int
    ) -> SubjectiveEvidence | None:
        db = self.db
        return db.scalar(
            select(SocialEventEvidence)
            .where(
                SocialEventEvidence.social_event_id == event_id,
                SocialEventEvidence.public_action_execution_id == execution_id,
            )
            .order_by(SocialEventEvidence.id)
            .limit(1)
        )
