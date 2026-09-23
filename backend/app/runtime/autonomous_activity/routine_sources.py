"""Resolve actual Routine source posts, not imaginary participants of a plan."""
from sqlalchemy import select
from app.domains.relationships.models.social import SocialEventEvidence
from app.runtime.social.manual_inbox import claimed_observation_post_id, is_manual_inbox_source
from app.runtime.relationships.social_metrics import prepare_sources


def source_manifest(ctx, prepared):
    ids = []
    for source in prepared.context.source_events:
        if is_manual_inbox_source(source.source_event_id):
            identifier = claimed_observation_post_id(ctx.db, source_event_id=source.source_event_id,
                world_id=prepared.world_character.world_id, consumer_world_character_id=prepared.world_character.id,
                target_activity_beat_id=prepared.beat.id, claim_run_id=ctx.run_id)
        else:
            identifier = ctx.db.scalar(select(SocialEventEvidence.source_post_id).where(
                SocialEventEvidence.social_event_id == source.source_event_id,
                SocialEventEvidence.source_post_id.is_not(None)).order_by(SocialEventEvidence.id))
        if identifier:
            ids.append(identifier)
    return prepare_sources(ctx.db, actor=prepared.world_character, post_ids=ids)
