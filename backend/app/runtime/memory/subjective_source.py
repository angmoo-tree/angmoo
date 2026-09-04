"""Reuse the SNS declaration validator; never infer another actor's motives."""

from dataclasses import asdict
import json

from sqlalchemy import and_, select

from app.domains.relationships.infrastructure.sqlalchemy_social_models import (
    SocialEvent,
    SocialEventEvidence,
)
from app.runtime.social.sqlalchemy_read_repository import (
    social_persistence_models as models,
)
from app.runtime.social.sqlalchemy_today_activity import (
    SqlAlchemyTodaySocialActivityReader,
)


def read_subjective_source(session, scope, *, source_type, source_id):
    evidence_table = SocialEventEvidence
    if source_type in {"POST", "REPLY"}:
        predicate = evidence_table.source_post_id == source_id
    elif source_type == "SOCIAL_EVENT":
        predicate = evidence_table.social_event_id == source_id
    elif source_type == "REACTION":
        reaction = session.get(models.PostLike, int(source_id))
        if (
            reaction is None
            or reaction.actor_world_character_id != scope.subject_world_character_id
        ):
            return None
        predicate = and_(
            evidence_table.source_object_type == "post_like",
            evidence_table.source_object_id == source_id,
        )
    else:
        return None
    pairs = session.execute(
        select(SocialEvent, evidence_table)
        .join(evidence_table, evidence_table.social_event_id == SocialEvent.id)
        .where(
            predicate,
            SocialEvent.world_id == scope.world_id,
            SocialEvent.actor_world_character_id == scope.subject_world_character_id,
            SocialEvent.result == "succeeded",
            SocialEvent.invalidated_at.is_(None),
            SocialEvent.retrieval_status == "eligible",
        )
        .order_by(SocialEvent.created_at.desc())
        .limit(8)
    ).all()
    if source_type in {"POST", "REPLY"}:
        pairs = [
            (event, evidence)
            for event, evidence in pairs
            if event.event_type
            in {"post_published", "reply_created", "comment_created"}
        ]
    if source_type == "REACTION":
        pairs = [
            (event, evidence)
            for event, evidence in pairs
            if event.event_type == "like_added"
        ]
    events = [pair[0] for pair in pairs]
    evidence = {pair[0].id: pair[1] for pair in pairs}
    execution_ids = [
        row.public_action_execution_id
        for row in evidence.values()
        if row.public_action_execution_id
    ]
    executions = {
        row.id: row
        for row in session.scalars(
            select(models.AgentPublicActionExecution).where(
                models.AgentPublicActionExecution.id.in_(execution_ids)
            )
        )
    }
    reader = SqlAlchemyTodaySocialActivityReader(session)
    validated = reader._subjective_by_event(
        scope.owner_id,
        scope.world_id,
        scope.subject_world_character_id,
        events,
        evidence,
        executions,
    )
    if not validated:
        return None
    # Only one actual action declaration is attached. IDs stay outside prompts.
    row = next(iter(validated.values()))
    payload = asdict(row)
    digest = payload.pop("source_digest")
    return digest, json.dumps(payload, ensure_ascii=False, sort_keys=True)
