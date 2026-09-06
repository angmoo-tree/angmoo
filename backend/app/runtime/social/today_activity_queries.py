"""Same-Session mixed World, membership, event and execution snapshot queries."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.domains.worlds.models import World, WorldMembership
from app.domains.world_characters.models import WorldCharacter
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.social.repository.today_activity import TodayActivityRepository
from app.domains.social.constants import _POST_EVENT_TYPES


class RuntimeTodayReferences:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._queries = TodayActivityRepository(db)

    def scope(self, world_id: str, subject_id: str):
        world = self._db.get(World, world_id, populate_existing=True)
        subject = self._db.get(WorldCharacter, subject_id, populate_existing=True)
        membership = (
            None
            if subject is None
            else self._db.get(
                WorldMembership, subject.membership_id, populate_existing=True
            )
        )
        return world, subject, membership

    def _active_world_character_ids(self, world_id):
        return set(
            self._db.scalars(
                select(WorldCharacter.id)
                .join(
                    WorldMembership,
                    WorldMembership.id == WorldCharacter.membership_id,
                )
                .where(
                    WorldCharacter.world_id == world_id,
                    WorldCharacter.status == "active",
                    WorldMembership.world_id == world_id,
                    WorldMembership.status == "active",
                )
            ).all()
        )

    def events(self, world_id, subject_world_character_id, start, end):
        return self._queries._bounded(
            select(SocialEvent)
            .where(
                SocialEvent.world_id == world_id,
                SocialEvent.occurred_at >= start,
                SocialEvent.occurred_at <= end,
                or_(
                    SocialEvent.actor_world_character_id == subject_world_character_id,
                    SocialEvent.target_world_character_id == subject_world_character_id,
                ),
            )
            .order_by(SocialEvent.occurred_at.desc(), SocialEvent.id)
        )

    def evidence(self, event_ids):
        return self._queries._by_ids(
            SocialEventEvidence, SocialEventEvidence.social_event_id, event_ids
        )

    def executions(self, execution_ids):
        return self._queries._by_ids(
            AgentPublicActionExecution, AgentPublicActionExecution.id, execution_ids
        )

    def represented_post_ids(self, world_id, post_ids):
        return self._db.scalars(
            select(SocialEventEvidence.source_post_id)
            .join(SocialEvent, SocialEvent.id == SocialEventEvidence.social_event_id)
            .where(
                SocialEvent.world_id == world_id,
                SocialEvent.event_type.in_(tuple(_POST_EVENT_TYPES)),
                SocialEventEvidence.source_post_id.in_(post_ids),
            )
        ).all()
