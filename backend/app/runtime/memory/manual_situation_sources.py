"""Bounded canonical source reads; authorization remains context/proof specific."""
from sqlalchemy import or_, select

from app.domains.memory.repository.access_batch import indexed, collection
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
from app.domains.relationships.service.source_event_evidence import manual_source_basis
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.social.models.posts import Post
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.social.constants import MAX_TODAY_BRANCH_DEPTH, _VISIBLE_POST_VISIBILITIES
from app.runtime.memory.source_queries import active_participant_ids


def prepare(validation, identifiers):
    events = indexed(validation, SocialEvent, SocialEvent.id, identifiers)
    events = [event for event in events if event.retrieval_status == "audit_only"]
    proofs = collection(validation, "manual_event_evidence", SocialEventEvidence,
                        SocialEventEvidence.social_event_id, (event.id for event in events))
    indexed(validation, AgentPublicActionExecution, AgentPublicActionExecution.id,
            (proof.public_action_execution_id for proof in proofs if proof.public_action_execution_id is not None))
    frontier = {identifier for proof in proofs for identifier in
                (proof.source_post_id, proof.target_post_id, proof.root_post_id) if identifier}
    seen = set()
    for _ in range(MAX_TODAY_BRANCH_DEPTH + 1):
        if not frontier:
            break
        rows = indexed(validation, Post, Post.id, frontier)
        seen.update(frontier)
        frontier = {row.reply_to_post_id for row in rows if row.reply_to_post_id} - seen


def basis(session, scope, event, validation):
    prepare(validation, (event.id,))
    proofs = validation.collections[("manual_event_evidence", event.id)]
    posts = {identifier: row for (model, identifier), row in validation.rows.items()
             if model is Post and row is not None}
    # One set query per prepared scope, not one query for each participant/event.
    participants = {scope.subject_world_character_id, event.actor_world_character_id,
                    event.target_world_character_id,
                    *(row.author_world_character_id for row in posts.values())} - {None}
    for (model, _), row in validation.rows.items():
        if model is SocialEvent and row is not None and row.world_id == scope.world_id:
            participants.update({row.actor_world_character_id, row.target_world_character_id} - {None})
    key = scope.world_id, frozenset(participants)
    if key not in validation.participants:
        validation.participants[key] = frozenset(active_participant_ids(session, participants, scope.world_id))
    missing = {identifier for identifier in participants - {scope.subject_world_character_id}
               if (scope.world_id, scope.subject_world_character_id, identifier) not in validation.blocks}
    if missing:
        rows = session.scalars(select(WorldCharacterBlock).where(
            WorldCharacterBlock.world_id == scope.world_id,
            or_((WorldCharacterBlock.blocker_world_character_id == scope.subject_world_character_id)
                & WorldCharacterBlock.blocked_world_character_id.in_(missing),
                (WorldCharacterBlock.blocked_world_character_id == scope.subject_world_character_id)
                & WorldCharacterBlock.blocker_world_character_id.in_(missing))))
        blocked = {identifier for row in rows for identifier in
                   (row.blocker_world_character_id, row.blocked_world_character_id)}
        for identifier in missing:
            validation.blocks[(scope.world_id, scope.subject_world_character_id, identifier)] = identifier in blocked
    blocked = {identifier for identifier in participants - {scope.subject_world_character_id}
               if validation.blocks[(scope.world_id, scope.subject_world_character_id, identifier)]}
    execution = (validation.get(AgentPublicActionExecution, proofs[0].public_action_execution_id)
                 if len(proofs) == 1 and proofs[0].public_action_execution_id is not None else None)
    return manual_source_basis(event, proofs, posts, world_id=scope.world_id,
        subject_id=scope.subject_world_character_id, active_ids=validation.participants[key],
        blocked_ids=blocked, max_depth=MAX_TODAY_BRANCH_DEPTH,
        allowed_visibilities=_VISIBLE_POST_VISIBILITIES, execution=execution)
