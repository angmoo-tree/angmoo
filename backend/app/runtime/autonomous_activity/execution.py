"""Execute a frozen V2 claim with inherited durable child checkpoints."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace
import sqlite3

from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
from app.domains.worlds.models import World, WorldMembership
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.binding import current
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
from app.runtime.autonomous_activity.contracts import ActivityIdentity
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.graph import build_autonomous_graph
from app.runtime.autonomous_activity.inbox import InboxLane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.social_lane import plain
from app.runtime.character_activity_state import initialize_from_last_success


class ActivityScopeChangedError(ValueError):
    pass


async def run_personalized_activity(ctx, *, actor, run, action_executor=None):
    binding = current()
    if binding is None:
        raise RuntimeError("personalized_activity_runtime_unavailable")
    lease_run_id = ctx.run_id
    if run.activity_id != lease_run_id:
        # New live slot owns recovery; effects retain the original canonical run ID.
        ctx = replace(ctx, run_id=run.activity_id)
    # Eight normal calls, plus at most two selected Inbox Writer splits.
    tracker = RunLlmTracker(max_calls=10)
    identity = ActivityIdentity(activity_id=run.activity_id, world_id=actor.world_id, actor_id=actor.id,
        cause="manual" if "manual" in ctx.session_key else "scheduled", generation_model=ctx.generation_model, thinking_level=ctx.generation_thinking_level).model_dump()

    async def guard(state):
        stored_identity = state.get("identity", identity)
        if any(stored_identity.get(key) != identity.get(key) for key in ("world_id", "actor_id", "generation_model", "thinking_level")):
            raise ActivityScopeChangedError("activity_identity_or_model_changed")
        ctx.db.expire_all()
        active = ctx.db.get(CharacterActiveWorld, ctx.character.id)
        current_actor = ctx.db.get(WorldCharacter, actor.id)
        world = ctx.db.get(World, actor.world_id)
        membership = ctx.db.get(WorldMembership, actor.membership_id)
        if (active is None or active.world_character_id != actor.id or current_actor is None
            or current_actor.world_id != identity["world_id"] or current_actor.control_mode != "autonomous"
            or current_actor.status != "active" or not current_actor.autonomous_enabled
            or world is None or world.status != "published" or world.readiness_status != "publish_ready"
            or membership is None or membership.status != "active" or membership.user_id != ctx.user_id):
            raise ActivityScopeChangedError("activity_scope_changed")
        row = ctx.db.get(ActivityGraphRun, run.activity_id)
        if row is None or row.engine != "personalized_graph_v2" or row.contract_version != 1:
            raise ActivityScopeChangedError("activity_contract_changed")
        from app.domains.routines.models import AgentRun, AgentSlot
        from app.domains.world_characters.service.activity_state import read_state, utc
        slot = ctx.db.get(AgentSlot, ctx.agent_id, populate_existing=True)
        canonical = ctx.db.get(AgentRun, lease_run_id, populate_existing=True)
        now = datetime.now(UTC)
        if (slot is None or canonical is None or canonical.status != "running"
            or slot.locked_by_run_id != lease_run_id or slot.assigned_character_id != ctx.character.id
            or slot.assigned_user_id != ctx.user_id or slot.lease_expires_at is None
            or utc(slot.lease_expires_at) <= now):
            raise ActivityScopeChangedError("activity_claim_lost")
        if state.get("stage") in {"ActionPlanner", "ValidateDecision", "Writer", "Execute"}:
            from app.runtime.autonomous_activity.revalidation import assert_memories_current
            assert_memories_current(ctx.db, owner_id=ctx.user_id, world_id=actor.world_id, actor_id=actor.id, memories=state.get("memories", {}))
            expected = state.get("shared_context", {}).get("current_state")
            if expected and read_state(ctx.db, world_id=actor.world_id, actor_id=actor.id)["version"] != expected["version"]:
                raise ActivityScopeChangedError("activity_state_changed")
        slot.lease_expires_at = now + timedelta(minutes=10)
        completed_paths = {path: state[f"{path}_result"] for path in ("inbox", "routine", "feed") if f"{path}_result" in state}
        if completed_paths:
            row.result = {**(row.result or {}), "paths": {**(row.result or {}).get("paths", {}), **completed_paths}}
        row.status = "running"
        row.stage = state.get("stage", "LoadContext")
        ctx.db.commit()
        return {}

    async def load(state):
        await guard(state)
        initialize_from_last_success(ctx.db, actor=actor)
        ctx.db.commit()
        return {"shared_context": plain(shared_input(ctx, actor, ctx.db.get(World, actor.world_id)))}

    async def finish(state):
        results = {path: state.get(f"{path}_result", {}) for path in ("inbox", "routine", "feed")}
        count = sum(r.get("public_action_count", 0) for r in results.values())
        result = {"engine": "personalized_graph_v2", "status": "failed" if any(r.get("status") == "failed" for r in results.values()) else "completed" if count else "observed",
            "summary": "Personalized Inbox, Routine and Feed graph completed.",
            "publish_result": {"public_action_count": count}, "paths": results,
            "llm_usage_summary": tracker.summary(), "llm_rate_limit_waits": tracker.rate_limit_waits}
        row = ctx.db.get(ActivityGraphRun, run.activity_id)
        row.status, row.stage, row.result, row.finished_at = result["status"], "Finalize", plain(result), datetime.now(UTC)
        ctx.db.commit()
        return {"result": result}

    adapters = {path: cls(ctx, actor=actor, tracker=tracker, hybrid_service=binding.hybrid_service, guard=guard,
                      **({"lane": path, "action_executor": action_executor} if path != "routine" else {}))
        for path, cls in (("inbox", InboxLane), ("routine", RoutineLane), ("feed", FeedLane))}
    lanes = {path: adapter.ports() for path, adapter in adapters.items()}
    for path, port in list(lanes.items()):
        async def failed(exc, lane=path):
            from app.integrations.direct_llm import DirectLlmDeferred, DirectLlmError
            from app.domains.social.exceptions import WorldFeedError
            if isinstance(exc, (ActivityScopeChangedError, DirectLlmDeferred)):
                raise exc
            if not isinstance(exc, (ValueError, DirectLlmError, WorldFeedError)):
                raise exc
            ctx.db.rollback()
            if lane == "feed":
                adapters[lane].observe_delivered()
            import re
            reason = str(exc) if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", str(exc)) else type(exc).__name__
            if lane == "routine":
                adapters[lane].release_failed(reason)
            row = ctx.db.get(ActivityGraphRun, run.activity_id)
            return {"path": lane, "status": "failed", "reason": reason, "failed_stage": row.stage, "public_action_count": 0}
        lanes[path] = replace(port, on_error=failed)
    async with activity_checkpointer(binding.data_directory) as saver:
        graph = build_autonomous_graph(lanes=lanes, load_context=load, refresh=load, finalize=finish, checkpointer=saver)
        config = checkpoint_config(activity_id=run.activity_id)
        checkpoint = await graph.aget_state(config)
        if checkpoint.values and not checkpoint.next and checkpoint.values.get("result"):
            return checkpoint.values["result"]
        try:
            await guard({"stage": "Resume" if checkpoint.values else "LoadContext", "identity": checkpoint.values.get("identity", identity)})
            final = await graph.ainvoke(None if checkpoint.values else {"identity": identity}, config)
        except BaseException as exc:
            ctx.db.rollback()
            row = ctx.db.get(ActivityGraphRun, run.activity_id)
            row.status = "aborted" if isinstance(exc, ActivityScopeChangedError) else "interrupted" if not isinstance(exc, Exception) else "waiting"
            if row.status == "aborted":
                row.finished_at = datetime.now(UTC)
            row.result = {**(row.result or {}), "reason": type(exc).__name__, "stage": row.stage}
            ctx.db.commit()
            raise
        from app.runtime.autonomous_activity.checkpoints import prune_completed
        try:
            await prune_completed(saver, ctx.db, now=datetime.now(UTC), keep_activity_id=run.activity_id)
        except (OSError, sqlite3.OperationalError):
            # Retention maintenance must not turn an already committed run into
            # a retry of its public effects. A later run retries pruning.
            import logging
            logging.getLogger(__name__).warning("activity_checkpoint_prune_deferred")
        return final["result"]
