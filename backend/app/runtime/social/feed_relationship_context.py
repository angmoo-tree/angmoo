"""Batch outgoing facts for the final candidate authors, independent of top-12 recall."""
from sqlalchemy import select
from app.domains.relationships.models.social import RelationshipState
from app.domains.relationships.contracts.social_context import SocialContextChangedError


def contexts(db, profile, author_ids):
    if len(author_ids) > 20:
        raise ValueError("feed_author_context_limit")
    rows = db.scalars(select(RelationshipState).where(
        RelationshipState.world_id == profile.world.id,
        RelationshipState.actor_world_character_id == profile.world_character.id,
        RelationshipState.target_world_character_id.in_(author_ids),
    ).execution_options(populate_existing=True)).all()
    return {row.target_world_character_id: {
        "relationship_label": row.relationship_label or "", "perception": row.perception or "",
        "direction": "actor_outgoing_only", "state_id": row.id, "version": row.version,
        "familiarity": row.familiarity, "affinity": row.affinity, "trust": row.trust, "tension": row.tension,
    } for row in rows}


def refresh(db, profile, candidates):
    facts = contexts(db, profile, {c.author_world_character_id for c in candidates})
    return tuple(c.model_copy(update={"relationship_context": facts.get(c.author_world_character_id)}) for c in candidates)


def validate(db, profile, candidates):
    facts = contexts(db, profile, {c.author_world_character_id for c in candidates})
    for candidate in candidates:
        if candidate.relationship_context != facts.get(candidate.author_world_character_id):
            raise SocialContextChangedError("feed_author_relationship_changed")
