"""Bounded read-only relationship progress for an already-authorized subject."""

from sqlalchemy import select, func
from app.domains.relationships.models.personalization import RelationshipPolicy, RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.models.social import RelationshipState


def read_review_status(db, *, world_id, actor_id, configuration):
    policy = db.get(RelationshipPolicy, world_id)
    roots = list(db.scalars(select(RelationshipReviewWork).where(
        RelationshipReviewWork.world_id == world_id, RelationshipReviewWork.actor_world_character_id == actor_id,
        RelationshipReviewWork.parent_id.is_(None)).order_by(RelationshipReviewWork.created_at.desc(),
            RelationshipReviewWork.id.desc()).limit(40)))
    excluded = dict(db.execute(select(RelationshipReviewMemoryReceipt.reason, func.count()).where(
        RelationshipReviewMemoryReceipt.world_id == world_id, RelationshipReviewMemoryReceipt.actor_world_character_id == actor_id,
        RelationshipReviewMemoryReceipt.status == 'excluded').group_by(RelationshipReviewMemoryReceipt.reason)).all())
    states = list(db.scalars(select(RelationshipState).where(RelationshipState.world_id == world_id,
        RelationshipState.actor_world_character_id == actor_id).order_by(RelationshipState.updated_at.desc()).limit(40)))
    return dict(mode=policy.mode if policy else 'legacy', activated_at=policy.activated_at if policy else None,
        configuration=configuration, excluded_counts=excluded,
        jobs=[dict(id=row.id, target_id=row.target_world_character_id, period=row.period_key, phase=row.phase,
                   status=row.status, error_code=row.error_code, next_attempt_at=row.next_attempt_at,
                   memory_count=len(row.manifest.get('memories', [])), completed_at=row.completed_at) for row in roots],
        states=[dict(target_id=row.target_world_character_id, last_metric_at=row.last_metric_at,
                     view_updated_at=row.view_updated_at, reviewed_at=row.reviewed_at) for row in states])
