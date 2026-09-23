"""Freeze identifiers and value objects, reattach canonical records on resume."""
from dataclasses import asdict
from datetime import UTC, datetime

from app.domains.routine_posts.contracts.context import RoutinePostContext
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.domains.routines.contracts.lifecycle import DueTick
from app.domains.routines.contracts.joint_activity import OpeningClaim
from app.domains.routines.models.plans import ActivityBeat, ActivityEpisode, DailyActivityPlan, DailyActivityPlanItem
from app.domains.routines.models.plans import JointActivity
from app.domains.social.models.posts import Post
from app.domains.world_characters.models import WorldCharacter, WorldCommunityProfile
from app.domains.worlds.models import World, WorldMembership
from app.runtime.autonomous_activity.social_lane import plain
from app.runtime.routine_posts.sqlalchemy_runtime import PreparedRoutine


def freeze_prepared(prepared):
    context = prepared.context
    return plain({"refs": {name: getattr(context, name).id if getattr(context, name) else None for name in (
            "world", "membership", "world_character", "profile", "plan", "item", "episode", "previous_beat", "previous_post")},
        "beat_id": prepared.beat.id, "joint_id": prepared.joint_activity.id if prepared.joint_activity else None,
        "opening_claim": asdict(prepared.opening_claim) if prepared.opening_claim else None,
        "claimed_manual_source_ids": prepared.claimed_manual_source_ids,
        "execution_signature": prepared.execution_signature,
        "due_tick": asdict(context.due_tick), "state_before": context.state_before, "common_state": context.common_state,
        "source_events": [asdict(e) for e in context.source_events],
        "eligible_event_count": context.eligible_event_count, "overflow_reason_counts": context.overflow_reason_counts,
        "prompt_comment_chars": context.prompt_comment_chars})


def restore_prepared(ctx, frozen, tracker):
    models = {"world": World, "membership": WorldMembership, "world_character": WorldCharacter,
        "profile": WorldCommunityProfile, "plan": DailyActivityPlan, "item": DailyActivityPlanItem,
        "episode": ActivityEpisode, "previous_beat": ActivityBeat, "previous_post": Post}
    records = {key: ctx.db.get(model, frozen["refs"][key], populate_existing=True) if frozen["refs"][key] else None for key, model in models.items()}
    if any(records[name] is None for name in models if not name.startswith("previous")):
        raise ValueError("routine_resume_source_missing")
    actor, world = records["world_character"], records["world"]
    beat = ctx.db.get(ActivityBeat, frozen["beat_id"], populate_existing=True)
    if actor.character_id != ctx.character.id or actor.world_id != world.id or beat is None or beat.world_id != world.id or beat.world_character_id != actor.id:
        raise ValueError("routine_resume_scope_changed")
    if beat.status not in {"claimed", "succeeded"} or (beat.status == "claimed" and beat.claim_run_id != ctx.run_id):
        raise ValueError("routine_resume_claim_changed")
    events = tuple(RoutineInteractionInput(**{**e, "occurred_at": datetime.fromisoformat(e["occurred_at"])}) for e in frozen["source_events"])
    due = frozen["due_tick"]
    context = RoutinePostContext(**records, character=ctx.character,
        due_tick=DueTick(datetime.fromisoformat(due["scheduled_for"]), due["skipped_tick_count"]),
        state_before=frozen["state_before"], source_events=events,
        eligible_event_count=frozen["eligible_event_count"], overflow_reason_counts=frozen["overflow_reason_counts"],
        prompt_comment_chars=frozen["prompt_comment_chars"], common_state=frozen.get("common_state"))
    opening = frozen["opening_claim"]
    opening = OpeningClaim(**{**opening, "expires_at": datetime.fromisoformat(opening["expires_at"])}) if opening else None
    joint = ctx.db.get(JointActivity, frozen["joint_id"]) if frozen["joint_id"] else None
    return PreparedRoutine(context, beat, actor, joint, opening, frozen["claimed_manual_source_ids"], frozen["execution_signature"], tracker, True)
