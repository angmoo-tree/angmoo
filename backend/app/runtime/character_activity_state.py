"""Verify a last successful routine state before adopting it as common state."""
from dataclasses import replace

from pydantic import ValidationError
from sqlalchemy import select

from app.domains.routines.models.plans import ActivityBeat
from app.domains.social.models.posts import Post
from app.domains.world_characters.activity_models import CharacterActivityState
from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.domains.world_characters.service.activity_state import read_state


def initialize_from_last_success(db, *, actor):
    """No AI/backfill. Preserve original completion time, including old dates."""
    if db.get(CharacterActivityState, actor.id) is not None:
        return
    beat = db.scalar(select(ActivityBeat).join(Post, Post.id == ActivityBeat.source_post_id).where(
        ActivityBeat.world_id == actor.world_id, ActivityBeat.world_character_id == actor.id,
        ActivityBeat.status == "succeeded", ActivityBeat.completed_at.is_not(None),
        Post.world_id == actor.world_id, Post.author_world_character_id == actor.id,
        Post.activity_beat_id == ActivityBeat.id, Post.deleted_at.is_(None),
    ).order_by(ActivityBeat.completed_at.desc(), ActivityBeat.id.desc()).limit(1))
    raw = beat.state_after_snapshot if beat is not None else None
    proposal = None
    if raw:
        try:
            proposal = StateUpdate.model_validate({"mood": raw.get("mood"), "mood_intensity": raw.get("mood_intensity"),
                "state_note": raw.get("action_note")})
        except ValidationError:
            pass
    db.add(CharacterActivityState(world_character_id=actor.id, world_id=actor.world_id,
        **(proposal.model_dump() if proposal else {}), version=1,
        changed_at=beat.completed_at if proposal else None, confirmed_at=beat.completed_at if proposal else None,
        origin=f"legacy_beat:{beat.id}" if proposal else None))
    db.flush()


def common_state_for_routine(db, *, context):
    """V1/V2 share three fields only; routine energy remains routine-owned."""
    existing = db.get(CharacterActivityState, context.world_character.id)
    if existing is None:
        return context
    snapshot = read_state(db, world_id=context.world.id, actor_id=context.world_character.id)
    state = dict(context.state_before)
    if snapshot["known"]:
        state.update(mood=snapshot["mood"], mood_intensity=snapshot["mood_intensity"], action_note=snapshot["state_note"])
    return replace(context, state_before=state, common_state=snapshot)


def settle_legacy_success(db, *, prepared, run_id, generation):
    """V2 participants returning to V1 retain one current state; no V1 backfill."""
    from app.domains.world_characters.service.activity_state import settle_state
    from hashlib import sha256
    def identity_key(*parts):
        return sha256("".join(f"{len(p)}:{p}" for p in parts).encode()).hexdigest()
    snapshot = prepared.context.common_state
    try:
        after = generation.state_after
        proposal = StateUpdate(mood=after["mood"], mood_intensity=after["mood_intensity"], state_note=after["action_note"])
    except (KeyError, ValidationError):
        return
    # V1's scheduled decay is not a new emotional experience. Carry state unless
    # a validated event effect actually changes one of the shared fields.
    changes = [e.state_change for e in generation.plan.source_event_effects]
    meaningful = any(c.mood is not None or c.mood_intensity_delta or c.action_note for c in changes)
    key = "routine_beat:" + prepared.beat.id
    settle_state(db, world_id=prepared.world_character.world_id, actor_id=prepared.world_character.id,
        activity_id=run_id, decision_key=identity_key(run_id, "legacy_routine", prepared.beat.id),
        expected_version=snapshot["version"], proposal=proposal if meaningful else None,
        judged_at=prepared.beat.completed_at, source_keys=[key], valid_source_keys={key})
