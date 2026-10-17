"""Bounded per-source declarations using the existing SNS validation policy."""
from sqlalchemy import func, select
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.social.models.posts import PostLike
from app.domains.social.repository.today_activity import TodayActivityRepository
from app.runtime.memory.subjective_source import validate_pairs


class _SubjectiveRows:
    def __init__(self, session, event_ids):
        ids = sorted(event_ids)
        repository = TodayActivityRepository(session)
        self.rows = [row for start in range(0, len(ids), 400)
            for row in repository.subjective(ids[start:start + 400])]

    def subjective(self, event_ids):
        ids = set(event_ids)
        return [row for row in self.rows if row.social_event_id in ids]


def read_subjective_batch(session, scope, identities):
    """Cap each source before event-type filtering, exactly like the scalar reader."""
    grouped, output = {}, dict.fromkeys(identities)
    table = SocialEventEvidence
    columns = {"POST": table.source_post_id, "REPLY": table.source_post_id,
               "SOCIAL_EVENT": table.social_event_id, "REACTION": table.source_object_id}
    for kind in columns:
        ids = sorted({identifier for source_type, identifier in identities if source_type == kind})
        for offset in range(0, len(ids), 400):
            chunk = ids[offset:offset + 400]
            predicates = [columns[kind].in_(chunk)]
            if kind == "REACTION":
                allowed = session.scalars(select(PostLike.id).where(
                    PostLike.id.in_([int(value) for value in chunk if value.isdecimal()]),
                    PostLike.actor_world_character_id == scope.subject_world_character_id))
                predicates = [columns[kind].in_([str(value) for value in allowed]), table.source_object_type == "post_like"]
            ranked = select(table.id.label("evidence_id"), columns[kind].label("source_id"),
                func.row_number().over(partition_by=columns[kind], order_by=SocialEvent.created_at.desc()).label("position")
                ).join(SocialEvent, SocialEvent.id == table.social_event_id).where(*predicates,
                    SocialEvent.world_id == scope.world_id,
                    SocialEvent.actor_world_character_id == scope.subject_world_character_id,
                    SocialEvent.result == "succeeded", SocialEvent.invalidated_at.is_(None),
                    SocialEvent.retrieval_status == "eligible").subquery()
            pairs = session.execute(select(SocialEvent, table, ranked.c.source_id).join(
                table, table.social_event_id == SocialEvent.id).join(ranked, ranked.c.evidence_id == table.id)
                .where(ranked.c.position <= 8).order_by(ranked.c.source_id, ranked.c.position)
                .execution_options(populate_existing=True))
            for event, evidence, identifier in pairs:
                grouped.setdefault((kind, identifier), []).append((event, evidence))
    event_ids = {event.id for pairs in grouped.values() for event, _ in pairs}
    repository = _SubjectiveRows(session, event_ids)
    execution_ids = sorted({evidence.public_action_execution_id for pairs in grouped.values()
        for _, evidence in pairs if evidence.public_action_execution_id})
    executions = {}
    for offset in range(0, len(execution_ids), 400):
        executions.update((row.id, row) for row in session.scalars(select(AgentPublicActionExecution).where(
            AgentPublicActionExecution.id.in_(execution_ids[offset:offset + 400]))
            .execution_options(populate_existing=True)))
    for identity, pairs in grouped.items():
        output[identity] = validate_pairs(session, scope, identity[0], pairs,
            repository=repository, executions=executions)
    return output
