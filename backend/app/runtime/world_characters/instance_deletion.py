"""One actor erasure, public tombstones and durable private-file cleanup."""
from datetime import UTC, datetime
from sqlalchemy import delete, or_, select, update
from app.models import Base
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.service.management import WorldManagementError
from app.domains.identity.models_world_credentials import WorldCredential, WorldCredentialRevision
from app.domains.identity.models_world_image_credentials import WorldImageProviderCredential
from app.domains.identity.service.environment import lock_environment_admission
from app.domains.media.models import MediaAsset, ImageInterpretation, InterpretationAttempt
from app.domains.media.models_world_policy import WorldImagePolicy, WorldImageAttempt
from app.domains.social.models.posts import Post, PostMedia, PostImageGenerationJob
from app.domains.social.models.image_intents import ImageIntent
from app.domains.routines.models import AgentSlot, AgentRun
from app.domains.chat.models import MessageAttachment


def erase(service, *, world_id, world_character_id, user, data):
    db = service.db
    try:
        lock_environment_admission(db, user.id)
        role, _ = service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, mutation=True)
        stored = db.get(WorldCharacterConfiguration, role.id)
        if not data.consent or stored is None or data.confirmed_name != stored.profile.get("display_name"):
            raise WorldManagementError("world_character_deletion_confirmation_required", 422)
        service._claim(role, data.expected_revision)
        now = datetime.now(UTC)
        # Slots are tied to the accepted actor, rather than every use of a source Character.
        slots = list(db.scalars(select(AgentSlot).where(AgentSlot.assigned_character_id == role.character_id)))
        owned_slots = [slot for slot in slots if (slot.admission_metadata or {}).get("_world_credential", {}).get("actor_id") == role.id]
        if any(slot.status == "running" and slot.lease_expires_at and slot.lease_expires_at.replace(tzinfo=UTC) > now for slot in owned_slots):
            raise WorldManagementError("world_character_deletion_busy")
        for slot in owned_slots:
            from app.domains.routines.service.slot_state import _clear_resident_slot
            _clear_resident_slot(slot)
        # Disable canonical access before purging children. Every async writer rechecks it.
        role.status, role.autonomous_enabled = "left", False
        db.execute(delete(CharacterActiveWorld).where(CharacterActiveWorld.world_character_id == role.id))
        own_credentials = select(WorldCredential.id).where(WorldCredential.owner_id == user.id,
            WorldCredential.world_id == world_id, WorldCredential.world_character_id == role.id)
        db.execute(delete(WorldCredentialRevision).where(WorldCredentialRevision.credential_id.in_(own_credentials)))
        db.execute(delete(WorldImageProviderCredential).where(WorldImageProviderCredential.owner_id == user.id,
            WorldImageProviderCredential.world_id == world_id, WorldImageProviderCredential.world_character_id == role.id))
        db.execute(delete(WorldCredential).where(WorldCredential.owner_id == user.id, WorldCredential.world_id == world_id,
            WorldCredential.world_character_id == role.id))
        from app.domains.memory.repository.privacy import erase_subject
        from app.domains.memory.models.items import MemoryItem
        from app.domains.relationships.models.personalization import RelationshipReviewMemoryReceipt
        own_memories = select(MemoryItem.id).where(MemoryItem.owner_id == user.id, MemoryItem.world_id == world_id,
            MemoryItem.subject_world_character_id == role.id)
        db.execute(delete(RelationshipReviewMemoryReceipt).where(RelationshipReviewMemoryReceipt.memory_id.in_(own_memories)))
        memory_ids = erase_subject(db, owner_id=user.id, world_id=world_id, actor_id=role.id)
        from app.domains.chat.service.privacy import erase_world_instance
        thread_ids = erase_world_instance(db, owner_id=user.id, world_id=world_id, actor_id=role.id)
        # Private caches disappear while public attachment assets remain available.
        analyses = list(db.scalars(select(ImageInterpretation.id).where(ImageInterpretation.owner_id == user.id,
            ImageInterpretation.scope_key.like(f"world-vision.v1|{world_id}|{role.id}|%"))))
        db.execute(update(MessageAttachment).where(MessageAttachment.interpretation_id.in_(analyses)).values(interpretation_id=None))
        db.execute(delete(InterpretationAttempt).where(InterpretationAttempt.interpretation_id.in_(analyses)))
        db.execute(delete(ImageInterpretation).where(ImageInterpretation.id.in_(analyses)))
        public_assets = select(PostMedia.asset_id).where(PostMedia.asset_id.is_not(None))
        private_assets = or_((MediaAsset.scope_kind == "world_character") & (MediaAsset.scope_id == role.id),
            (MediaAsset.scope_kind == "thread") & MediaAsset.scope_id.in_(thread_ids))
        db.execute(update(MediaAsset).where(MediaAsset.owner_id == user.id, private_assets, MediaAsset.id.not_in(public_assets))
            .values(state="deleted"))
        posts = select(Post.id).where(Post.world_id == world_id, Post.author_world_character_id == role.id)
        jobs = list(db.scalars(select(PostImageGenerationJob.id).where(PostImageGenerationJob.post_id.in_(posts))))
        unattached = select(PostImageGenerationJob.result_asset_id).where(PostImageGenerationJob.id.in_(jobs),
            PostImageGenerationJob.result_asset_id.is_not(None))
        db.execute(update(MediaAsset).where(MediaAsset.owner_id == user.id, MediaAsset.id.in_(unattached),
            MediaAsset.id.not_in(public_assets)).values(state="deleted"))
        db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.post_id.in_(posts),
            PostImageGenerationJob.status.in_(("queued", "running", "result_pending", "result_ready", "outcome_unknown")))
            .values(status="failed", lease_token=None, lease_until=None, skip_reason="world_character_deleted"))
        db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id.in_(jobs)).values(image_prompt=""))
        db.execute(update(ImageIntent).where(ImageIntent.post_id.in_(posts)).values(scene="", request_json="{}",
            credential_id=None, credential_revision=None))
        db.execute(delete(WorldImageAttempt).where(WorldImageAttempt.world_character_id == role.id))
        db.execute(delete(WorldImagePolicy).where(WorldImagePolicy.world_character_id == role.id))
        _scrub_private_execution(db, role)
        role.local_profile = {"deleted": True, "private_cleanup": {"interpretations": analyses, "generation_jobs": jobs}}
        db.execute(delete(WorldCharacterConfiguration).where(WorldCharacterConfiguration.world_character_id == role.id))
        db.flush()
        db.commit()
    except BaseException:
        db.rollback()
        raise
    # Cleanup is retryable from the deleted asset rows; it cannot roll back erasure.
    from app.runtime.media.binding import current
    media = current()
    if media:
        media.cleanup_deleted_assets()
    return {"contract_version": "world-character-instance-delete-v1", "world_id": world_id,
        "world_character_id": role.id, "deleted": True, "public_material_preserved": True,
        "private_memory_count": len(memory_ids)}


def _scrub_private_execution(db, role):
    """Only named, actor-owned private tables; public effects and other subjects stay."""
    actor, world = role.id, role.world_id
    tables = Base.metadata.tables
    for name in ("world_character_activity_states", "world_character_state_receipts", "activity_engine_policies"):
        table = tables[name]
        db.execute(delete(table).where(table.c.world_character_id == actor))
    graph = tables["activity_graph_runs"]
    db.execute(update(graph).where(graph.c.world_character_id == actor, graph.c.world_id == world)
        .values(status="cancelled", stage="privacy_erasure", result=None))
    prep = tables["activity_preparation_jobs"]
    db.execute(update(prep).where(prep.c.world_character_id == actor, prep.c.world_id == world)
        .values(state="failed", claim_token=None, lease_expires_at=None, next_retry_at=None,
            input_snapshot={}, applied_snapshot={}, usage_snapshot={}, reason_code="world_character_deleted", version=prep.c.version + 1))
    plans = tables["daily_activity_plans"]
    db.execute(update(plans).where(plans.c.world_character_id == actor, plans.c.world_id == world).values(status="cancelled", version=plans.c.version + 1))
    items = tables["daily_activity_plan_items"]
    db.execute(update(items).where(items.c.world_character_id == actor, items.c.world_id == world)
        .values(title="", activity_seed="", status="cancelled", terminal_reason_code="world_character_deleted", version=items.c.version + 1))
    episodes = tables["activity_episodes"]
    db.execute(update(episodes).where(episodes.c.world_character_id == actor, episodes.c.world_id == world)
        .values(effective_activity_snapshot={}, current_state_snapshot={}, completion_summary=None,
            status="cancelled", terminal_reason_code="world_character_deleted", version=episodes.c.version + 1))
    beats = tables["activity_beats"]
    db.execute(update(beats).where(beats.c.world_character_id == actor, beats.c.world_id == world)
        .values(state_before_snapshot={}, state_after_snapshot={}, result_snapshot={}, source_event_ids=[], claim_run_id=None, claim_expires_at=None))
    topic = tables["social_recommendation_preparations"]
    db.execute(update(topic).where(topic.c.world_character_id == actor, topic.c.world_id == world)
        .values(state="failed", request_snapshot=None, lease_expires_at=None, last_code="world_character_deleted"))
    # Thoughts belong to this actor. Retain only the receipt identity used by public effects.
    thought = tables["social_activity_thoughts"]
    db.execute(update(thought).where(thought.c.actor_world_character_id == actor)
        .values(thought_text=None, status="missing", truncated=False))
    for name in ("social_recommendation_deliveries", "social_recommendation_topic_sources", "world_character_feed_cursors"):
        table = tables[name]
        db.execute(delete(table).where(table.c.world_character_id == actor))
    # Candidate rows are private, but plan receipts can retain their identities.
    candidates = tables["world_activity_candidates"]
    repertoires = tables["world_activity_repertoires"]
    ids = select(repertoires.c.id).where(repertoires.c.world_character_id == actor)
    private_candidate_fields = {c.name: None if c.nullable else [] if str(c.type) == "JSON" else ""
        for c in candidates.c if c.name in {"title", "activity_seed", "description", "place_key", "tags"}}
    if private_candidate_fields:
        db.execute(update(candidates).where(candidates.c.repertoire_id.in_(ids)).values(**private_candidate_fields))
    db.execute(update(repertoires).where(repertoires.c.world_character_id == actor).values(status="failed", validation_summary={}))
    community = tables["world_community_profiles"]
    db.execute(update(community).where(community.c.world_character_id == actor).values(status="failed", visible_summary="",
        core_interests=[], adjacent_interests=[], avoid_topics=[], search_keywords=[], action_profile={}))
    relationships = tables["relationship_states"]
    db.execute(update(relationships).where(relationships.c.actor_world_character_id == actor)
        .values(relationship_label=None, perception=None))
    review = tables["relationship_review_work"]
    db.execute(update(review).where(review.c.actor_world_character_id == actor)
        .values(status="failed", manifest={}, result=None, lease_token=None, lease_until=None, next_attempt_at=None,
            error_code="world_character_deleted"))
    runs = db.scalars(select(AgentRun).where(AgentRun.character_id == role.character_id, AgentRun.user_id.is_not(None)))
    for run in runs:
        if (run.input_snapshot or {}).get("_world_credential", {}).get("actor_id") == actor:
            run.input_snapshot, run.gateway_result, run.tool_auth_key = {}, {}, None
            if run.status in {"queued", "running", "accepted"}:
                run.status, run.completed_at = "failed", datetime.now(UTC)
