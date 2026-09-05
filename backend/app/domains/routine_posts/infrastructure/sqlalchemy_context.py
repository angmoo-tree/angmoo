from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compatibility.routine_posts import legacy
from app.domains.routines.contracts.lifecycle import DueTick, EVENT_CONSUMPTION_NAMESPACE
from app.domains.routines.service.scheduling import latest_due_tick
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.domains.routine_posts.constants import MAX_SOURCE_EVENTS, MAX_EVENT_EXCERPT_CHARS, MAX_TOTAL_EVENT_EXCERPT_CHARS, MAX_EVENT_CONTEXT_JSON_BYTES
from app.domains.routine_posts.exceptions import RoutineContextUnavailable
from app.domains.routine_posts.service.event_context import _bounded_events, _relationship_rank
from app.domains.routine_posts.utils.text import _clip
from app.domains.routines.service.scheduling import aware_utc as _aware_utc


models = legacy.models
activity_state_contracts = legacy.activity_state_contracts
neutralize_context_text = legacy.neutralize_context_text




class RoutineInteractionSource(Protocol):
    def candidates(
        self,
        db: Session,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[RoutineInteractionInput]: ...


class EmptyRoutineInteractionSource:
    def candidates(
        self,
        db: Session,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[RoutineInteractionInput]:
        del db, world_id, consumer_world_character_id, episode_id, after, before
        return []


@dataclass(frozen=True)
class RoutinePostContext:
    world: models.World
    membership: models.WorldMembership
    world_character: models.WorldCharacter
    character: models.Character
    profile: models.WorldCommunityProfile
    plan: models.DailyActivityPlan
    item: models.DailyActivityPlanItem
    episode: models.ActivityEpisode
    due_tick: DueTick
    previous_beat: models.ActivityBeat | None
    previous_post: models.Post | None
    state_before: dict[str, object]
    source_events: tuple[RoutineInteractionInput, ...]
    eligible_event_count: int
    overflow_reason_counts: dict[str, int]
    prompt_comment_chars: int

    @property
    def considered_source_event_ids(self) -> list[str]:
        return [event.source_event_id for event in self.source_events]






def assemble_routine_post_context(
    db: Session,
    *,
    world_character: models.WorldCharacter,
    character: models.Character,
    now: datetime,
    interaction_source: RoutineInteractionSource | None = None,
) -> RoutinePostContext:
    current = _aware_utc(now)
    if world_character.status != "active":
        raise RoutineContextUnavailable("WORLD_SCOPE_INVALID")
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        raise RoutineContextUnavailable("MEMBERSHIP_INACTIVE")
    world = db.get(models.World, world_character.world_id)
    if world is None or world.status != "published" or world.readiness_status != "publish_ready":
        raise RoutineContextUnavailable("WORLD_SCOPE_INVALID")

    item = db.scalar(
        select(models.DailyActivityPlanItem).where(
            models.DailyActivityPlanItem.world_character_id == world_character.id,
            models.DailyActivityPlanItem.scheduled_start_at <= current,
            models.DailyActivityPlanItem.scheduled_end_at > current,
            models.DailyActivityPlanItem.status.in_({"planned", "active"}),
        )
    )
    if item is None:
        raise RoutineContextUnavailable("NO_ROUTINE_CONTEXT")
    plan = db.get(models.DailyActivityPlan, item.plan_id)
    episode = db.scalar(
        select(models.ActivityEpisode).where(
            models.ActivityEpisode.plan_item_id == item.id
        )
    )
    if (
        plan is None
        or episode is None
        or plan.world_id != world.id
        or episode.world_id != world.id
        or episode.world_character_id != world_character.id
        or episode.status not in {"planned", "active"}
    ):
        raise RoutineContextUnavailable("NO_ROUTINE_CONTEXT")

    repertoire = db.get(models.WorldActivityRepertoire, plan.repertoire_id)
    profile = (
        db.get(models.WorldCommunityProfile, repertoire.community_profile_id)
        if repertoire is not None
        else None
    )
    if repertoire is None or profile is None or profile.status != "ready":
        raise RoutineContextUnavailable("NO_ROUTINE_CONTEXT")

    previous_beat = (
        db.get(models.ActivityBeat, episode.last_successful_beat_id)
        if episode.last_successful_beat_id is not None
        else None
    )
    previous_post = (
        db.get(models.Post, previous_beat.source_post_id)
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

    latest_beat = db.scalar(
        select(models.ActivityBeat)
        .where(models.ActivityBeat.episode_id == episode.id)
        .order_by(models.ActivityBeat.scheduled_for.desc(), models.ActivityBeat.id.desc())
        .limit(1)
    )
    setting = db.get(models.AgentActivitySetting, character.id)
    interval_minutes = setting.activity_interval_minutes if setting is not None else 60
    retry_beat: models.ActivityBeat | None = None
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
        source = legacy.canonical_interaction_source()
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
        for consumption in db.scalars(
            select(models.ActivityEventConsumption).where(
                models.ActivityEventConsumption.consumer_world_character_id
                == world_character.id,
                models.ActivityEventConsumption.source_social_event_id.in_(event_ids),
                models.ActivityEventConsumption.namespace
                == EVENT_CONSUMPTION_NAMESPACE,
            )
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
