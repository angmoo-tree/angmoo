"""Routine scope, retry continuity and bounded source-event context policy."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from app.domains.routine_posts.contracts.context import RoutineContextReferences, RoutineInteractionSource, RoutinePostContext
from app.domains.routine_posts.exceptions import RoutineContextUnavailable
from app.domains.routine_posts.service.event_context import _bounded_events
from app.domains.routines.contracts.lifecycle import DueTick
from app.domains.routines.service.scheduling import aware_utc as _aware_utc, latest_due_tick
from app.domains.routines import service as activity_state_contracts


def assemble_routine_post_context(
    db: Any,
    *,
    references: RoutineContextReferences,
    world_character: Any,
    character: Any,
    now: datetime,
    interaction_source: RoutineInteractionSource | None = None,
) -> RoutinePostContext:
    current = _aware_utc(now)
    if world_character.status != "active":
        raise RoutineContextUnavailable("WORLD_SCOPE_INVALID")
    membership = references.get_membership(world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        raise RoutineContextUnavailable("MEMBERSHIP_INACTIVE")
    world = references.get_world(world_character.world_id)
    if world is None or world.status != "published" or world.readiness_status != "publish_ready":
        raise RoutineContextUnavailable("WORLD_SCOPE_INVALID")

    item = references.current_item(world_character_id=world_character.id, current=current)
    if item is None:
        raise RoutineContextUnavailable("NO_ROUTINE_CONTEXT")
    plan = references.get_plan(item.plan_id)
    episode = references.episode_for_item(item.id)
    if (
        plan is None
        or episode is None
        or plan.world_id != world.id
        or episode.world_id != world.id
        or episode.world_character_id != world_character.id
        or episode.status not in {"planned", "active"}
    ):
        raise RoutineContextUnavailable("NO_ROUTINE_CONTEXT")

    repertoire = references.get_repertoire(plan.repertoire_id)
    profile = (
        references.get_profile(repertoire.community_profile_id)
        if repertoire is not None
        else None
    )
    if repertoire is None or profile is None or profile.status != "ready":
        raise RoutineContextUnavailable("NO_ROUTINE_CONTEXT")

    previous_beat = (
        references.get_beat(episode.last_successful_beat_id)
        if episode.last_successful_beat_id is not None
        else None
    )
    previous_post = (
        references.get_post(previous_beat.source_post_id)
        if previous_beat is not None and previous_beat.source_post_id is not None
        else None
    )
    if previous_beat is not None and (
        previous_beat.status != "succeeded"
        or previous_beat.world_id != world.id
        or previous_beat.world_character_id != world_character.id
        or previous_post is None
        or previous_post.world_id != world.id
        or previous_post.author_world_character_id != world_character.id
    ):
        raise RoutineContextUnavailable("WORLD_SCOPE_INVALID")

    latest_beat = references.latest_beat(episode.id)
    setting = references.get_activity_setting(character.id)
    interval_minutes = setting.activity_interval_minutes if setting is not None else 60
    retry_beat: Any | None = None
    if latest_beat is not None and latest_beat.status == "claimed":
        claim_expiry = (
            _aware_utc(latest_beat.claim_expires_at)
            if latest_beat.claim_expires_at is not None
            else current
        )
        if claim_expiry > current:
            raise RoutineContextUnavailable("BEAT_ALREADY_CLAIMED")
        retry_beat = latest_beat
    elif latest_beat is not None and latest_beat.status == "pending":
        retry_beat = latest_beat

    due_tick = (
        DueTick(
            scheduled_for=_aware_utc(retry_beat.scheduled_for),
            skipped_tick_count=retry_beat.skipped_tick_count,
        )
        if retry_beat is not None
        else latest_due_tick(
            window_start=item.scheduled_start_at,
            window_end=item.scheduled_end_at,
            now=current,
            activity_interval_minutes=interval_minutes,
            last_scheduled_for=(
                latest_beat.scheduled_for if latest_beat is not None else None
            ),
        )
    )
    if due_tick is None:
        raise RoutineContextUnavailable("BEAT_NOT_DUE")

    cutoff = (
        _aware_utc(previous_beat.completed_at)
        if previous_beat is not None and previous_beat.completed_at is not None
        else _aware_utc(item.scheduled_start_at)
    )
    if interaction_source is None:
        source = references.default_interaction_source()
    else:
        source = interaction_source
    raw_events = source.candidates(
        db,
        world_id=world.id,
        consumer_world_character_id=world_character.id,
        episode_id=episode.id,
        after=cutoff,
        before=current,
    )
    event_ids = list(dict.fromkeys(event.source_event_id for event in raw_events))
    blocked_event_ids: set[str] = set()
    if event_ids:
        for consumption in references.event_consumptions(
            world_character_id=world_character.id, event_ids=event_ids,
        ):
            active_claim = (
                consumption.status == "claimed"
                and consumption.claim_expires_at is not None
                and _aware_utc(consumption.claim_expires_at) > current
            )
            if consumption.status in {"applied", "rejected"} or active_claim:
                blocked_event_ids.add(consumption.source_social_event_id)

    if retry_beat is not None:
        candidates_by_id = {event.source_event_id: event for event in raw_events}
        missing_ids = [
            event_id
            for event_id in retry_beat.source_event_ids
            if event_id not in candidates_by_id
        ]
        if missing_ids:
            raise RoutineContextUnavailable("SOURCE_EVENT_CONTEXT_MISSING")
        raw_events = [
            candidates_by_id[event_id] for event_id in retry_beat.source_event_ids
        ]
        blocked_event_ids.difference_update(retry_beat.source_event_ids)

    selected_events, overflow_reasons, prompt_chars, eligible_event_count = _bounded_events(
        raw_events,
        world_id=world.id,
        consumer_world_character_id=world_character.id,
        after=cutoff,
        before=current,
        blocked_event_ids=blocked_event_ids,
    )
    if retry_beat is not None and [
        event.source_event_id for event in selected_events
    ] != retry_beat.source_event_ids:
        raise RoutineContextUnavailable("SOURCE_EVENT_CONTEXT_MISSING")
    return RoutinePostContext(
        world=world,
        membership=membership,
        world_character=world_character,
        character=character,
        profile=profile,
        plan=plan,
        item=item,
        episode=episode,
        due_tick=due_tick,
        previous_beat=previous_beat,
        previous_post=previous_post,
        state_before=activity_state_contracts.validate_state_snapshot(
            episode.current_state_snapshot
        ),
        source_events=selected_events,
        eligible_event_count=eligible_event_count,
        overflow_reason_counts=overflow_reasons,
        prompt_comment_chars=prompt_chars,
    )
