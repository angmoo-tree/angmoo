"""Execute a frozen V2 claim with inherited durable child checkpoints."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace
import sqlite3

from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
from app.domains.worlds.models import World, WorldMembership
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.binding import current, observer
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
from app.runtime.autonomous_activity.contracts import ActivityIdentity
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.graph import build_autonomous_graph
from app.runtime.autonomous_activity.inbox import InboxLane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.output_recovery import MAX_CALL_BUDGET
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
    # Diagnostics are optional and cannot hold the activity's execution lease.
    try:
        sink = observer()
        attempt = sink.begin(activity_id=run.activity_id, agent_run_id=lease_run_id,
            world_id=actor.world_id, actor_id=actor.id, activity_started_at=run.started_at) if sink else None
    except Exception:
        attempt = None
    # Normal graph budget plus one bounded recovery for each eligible node.
    tracker = RunLlmTracker(max_calls=MAX_CALL_BUDGET, observer=attempt.tracker_event if attempt else None)
    identity = ActivityIdentity(activity_id=run.activity_id, world_id=actor.world_id, actor_id=actor.id,
        contract_version=run.contract_version,
        cause="manual" if "manual" in ctx.session_key else "scheduled", generation_model=ctx.generation_model, thinking_level=ctx.generation_thinking_level).model_dump()
    policy = (run.result or {}).get("routine_policy")
    from app.contracts.name_binding import read_name_binding
    from app.domains.world_characters.service.name_binding import validate_name_binding
    name_binding = read_name_binding(run.result)
    frozen_names = (run.result or {}).get("name_binding")
    name_policy = (run.result or {}).get("name_binding_policy")
    if policy is not None:
        identity.update(routine_output_contract=policy["output_contract"], routine_state_schema_version=policy["state_schema_version"], routine_thought_policy=policy["thought_policy"])
    if attempt:
        attempt.emit("activity_identity", details={
            "cause": identity["cause"], "contract_version": identity["contract_version"],
            "generation_model": identity["generation_model"],
            "thinking_level": identity["thinking_level"], "routine_output_contract": identity["routine_output_contract"],
            "routine_state_schema_version": identity["routine_state_schema_version"], "routine_thought_policy": identity["routine_thought_policy"]})

    def validate_claim():
        """Read-only claim fence; also runs inside each fresh writer boundary."""
        active = ctx.db.get(CharacterActiveWorld, ctx.character.id, populate_existing=True)
        current_actor = ctx.db.get(WorldCharacter, actor.id, populate_existing=True)
        world = ctx.db.get(World, actor.world_id, populate_existing=True)
        membership = ctx.db.get(WorldMembership, actor.membership_id, populate_existing=True)
        if (active is None or active.world_character_id != actor.id or current_actor is None
            or current_actor.world_id != identity["world_id"] or current_actor.control_mode != "autonomous"
            or current_actor.status != "active" or not current_actor.autonomous_enabled
            or world is None or world.status != "published" or world.readiness_status != "publish_ready"
            or membership is None or membership.status != "active" or membership.user_id != ctx.user_id):
            raise ActivityScopeChangedError("activity_scope_changed")
        row = ctx.db.get(ActivityGraphRun, run.activity_id, populate_existing=True)
        if row is None or row.engine != "personalized_graph_v2" or row.contract_version != identity["contract_version"]:
            raise ActivityScopeChangedError("activity_contract_changed")
        if (row.result or {}).get("routine_policy") != policy:
            raise ActivityScopeChangedError("routine_policy_changed")
        if (row.result or {}).get("name_binding") != frozen_names:
            raise ActivityScopeChangedError("name_binding_changed")
        if (row.result or {}).get("name_binding_policy") != name_policy:
            raise ActivityScopeChangedError("name_binding_changed")
        if name_binding is not None:
            validate_name_binding(ctx.db, name_binding, actor=current_actor, owner_id=ctx.user_id)
        from app.domains.routines.models import AgentRun, AgentSlot
        from app.domains.world_characters.service.activity_state import utc
        slot = ctx.db.get(AgentSlot, ctx.agent_id, populate_existing=True)
        canonical = ctx.db.get(AgentRun, lease_run_id, populate_existing=True)
        now = datetime.now(UTC)
        if (slot is None or canonical is None or canonical.status != "running"
            or slot.locked_by_run_id != lease_run_id or slot.assigned_character_id != ctx.character.id
            or slot.assigned_user_id != ctx.user_id or slot.lease_expires_at is None
            or utc(slot.lease_expires_at) <= now):
            raise ActivityScopeChangedError("activity_claim_lost")
        return row, slot, now

    async def guard(state):
        stored_identity = state.get("identity", identity)
        if any(stored_identity.get(key) != identity.get(key) for key in ("activity_id", "contract_version", "world_id", "actor_id", "generation_model", "thinking_level", "routine_output_contract", "routine_state_schema_version", "routine_thought_policy")):
            raise ActivityScopeChangedError("activity_identity_or_model_changed")
        ctx.db.expire_all()
        row, slot, now = validate_claim()
        if state.get("stage") in {"ActionPlanner", "DecisionDraft", "ValidateDecision", "Writer", "ValidateDraft", "Execute"}:
            from app.domains.world_characters.service.activity_state import read_state
            from app.runtime.autonomous_activity.revalidation import assert_memories_current
            if any(value.get("packets") and target not in state.get("memory_validations", {})
                   for target, value in state.get("memories", {}).items()):
                raise ActivityScopeChangedError("activity_memory_validation_unavailable")
            assert_memories_current(ctx.db, owner_id=ctx.user_id, world_id=actor.world_id, actor_id=actor.id,
                memories=state.get("memories", {}), validations=state.get("memory_validations", {}))
            expected = state.get("shared_context", {}).get("current_state")
            if expected and read_state(ctx.db, world_id=actor.world_id, actor_id=actor.id)["version"] != expected["version"]:
                raise ActivityScopeChangedError("activity_state_changed")
        slot.lease_expires_at = now + timedelta(minutes=10)
        completed_paths = {path: state[f"{path}_result"] for path in ("inbox", "routine", "feed") if f"{path}_result" in state}
        if completed_paths:
            row.result = {**(row.result or {}), "paths": {**(row.result or {}).get("paths", {}), **completed_paths}}
        row.status = "running"
        row.result = {**(row.result or {}), "contract_version": identity["contract_version"]}
        row.stage = state.get("stage", "LoadContext")
        ctx.db.commit()
        return {}

    preparation_status = {}

    async def load(state):
        await guard(state)
        from app.config import settings
        if settings.DAILY_PREPARATION_ENABLED and not state.get("shared_context"):
            from types import SimpleNamespace
            from app.runtime.daily_preparation import ensure_preparation
            # Startup/manual execution and scheduler midnight share the same claim.
            prepared = await ensure_preparation(ctx.db, character_id=ctx.character.id, world_id=actor.world_id,
                                     user=SimpleNamespace(id=ctx.user_id))
            preparation_status.update(prepared.model_dump(mode="json"))
            if attempt:
                attempt.emit("daily_preparation", details=preparation_status)
            ctx.db.expire_all()
        initialize_from_last_success(ctx.db, actor=actor)
        ctx.db.commit()
        shared = plain(shared_input(ctx, actor, ctx.db.get(World, actor.world_id)))
        if attempt and name_binding is not None:
            attempt.emit("name_binding", details={"policy_version": name_binding.policy_version,
                "binding_digest": name_binding.digest, "profile_version": name_binding.user_profile_version,
                "fields": shared["persona"]["name_binding"]["fields"]})
        return {"shared_context": shared}

    async def finish(state):
        results = {path: state.get(f"{path}_result", {}) for path in ("inbox", "routine", "feed")}
        count = sum(r.get("public_action_count", 0) for r in results.values())
        result = {"engine": "personalized_graph_v2", "contract_version": identity["contract_version"],
            "execution_order": ["inbox", "feed", "routine"] if identity["contract_version"] == 2 else ["inbox", "routine", "feed"],
            "status": "failed" if any(r.get("status") == "failed" for r in results.values()) else "completed" if count else "observed",
            "summary": "Personalized Inbox, Routine and Feed graph completed.",
            "publish_result": {"public_action_count": count}, "paths": results,
            "llm_usage_summary": tracker.summary(), "llm_rate_limit_waits": tracker.rate_limit_waits,
            "daily_preparation": preparation_status}
        row = ctx.db.get(ActivityGraphRun, run.activity_id)
        result = {**(row.result or {}), **result}
        row.status, row.stage, row.result, row.finished_at = result["status"], "Finalize", plain(result), datetime.now(UTC)
        ctx.db.commit()
        if attempt:
            attempt.emit("activity_result", classification=result["status"], details={
                "status": result["status"], "public_action_count": count,
                "paths": {path: {"status": item.get("status"),
                    "public_action_count": item.get("public_action_count", 0)} for path, item in results.items()}})
        return {"result": result}

    classes = (("inbox", InboxLane), ("routine", RoutineLane), ("feed", FeedLane))
    version_options = {}
    if identity["contract_version"] == 2:
        from app.runtime.autonomous_activity.combined_lanes import CombinedInboxLane, CombinedFeedLane, CombinedRoutineLane
        from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
        classes = (("inbox", CombinedInboxLane), ("routine", CombinedRoutineLane), ("feed", CombinedFeedLane))
        version_options = {"ledger": RecoveryLedger(ctx.db, run.activity_id)}
    adapters = {path: cls(ctx, actor=actor, tracker=tracker, hybrid_service=binding.hybrid_service,
                      guard=guard, claim_validator=validate_claim,
                      **version_options,
                      **({"lane": path, "action_executor": action_executor} if path != "routine" else {}))
        for path, cls in classes}
    lanes = {path: adapter.ports() for path, adapter in adapters.items()}
    for path, port in list(lanes.items()):
        async def failed(exc, lane=path):
            from app.integrations.direct_llm import DirectLlmDeferred, DirectLlmError
            from app.domains.social.exceptions import WorldFeedError
            if attempt:
                attempt.emit("lane_error", lane=lane, classification="deferred" if isinstance(exc, DirectLlmDeferred) else "failed",
                    exc=exc, caused_by_event_id=attempt.last_error_event_id)
            if isinstance(exc, (ActivityScopeChangedError, DirectLlmDeferred)):
                raise exc
            if not isinstance(exc, (ValueError, DirectLlmError, WorldFeedError)):
                raise exc
            ctx.db.rollback()
            if lane == "feed":
                original_error_id = attempt.last_error_event_id if attempt else None
                try:
                    adapters[lane].observe_delivered()
                    if identity["contract_version"] == 2:
                        adapters[lane].reconcile_deliveries()
                except Exception as cleanup_error:
                    if attempt:
                        attempt.emit("feed_observation_cleanup_error", lane="feed", classification="failed",
                            exc=cleanup_error, caused_by_event_id=original_error_id)
                    raise cleanup_error from exc
            import re
            reason = str(exc) if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", str(exc)) else type(exc).__name__
            if lane == "routine":
                adapters[lane].release_failed(reason)
            row = ctx.db.get(ActivityGraphRun, run.activity_id)
            stale = identity["contract_version"] == 2 and lane == "feed" and reason in {
                "feed_target_stale", "activity_source_changed", "feed_affordance_changed", "feed_claim_changed"}
            return {"path": lane, "status": "no_action" if stale else "failed", "reason": reason,
                "failed_stage": row.stage, "public_action_count": 0,
                **({"feed_summary": adapters[lane].finalize_unavailable(reason)} if stale else {})}
        def trace(event_type, name, *, path=path, **details):
            if attempt:
                attempt.node(event_type, lane=path, node=name, **details)
        lanes[path] = replace(port, on_error=failed, observe=trace)
    graph_options = {}
    if identity["contract_version"] == 2:
        from app.runtime.autonomous_activity.combined_selection import CombinedSelection
        selection = CombinedSelection(adapters, dict(lanes))
        graph_options = {"prepare": selection.prepare, "choose_selection_mode": selection.mode,
            "combined_select": selection.select}
        for path in ("inbox", "feed"):
            port = lanes[path]
            async def use_prepared(state, lane=path):
                if state.get("preparation_error"):
                    return {}
                if lane == "feed":
                    return await adapters[lane].refresh_selected(state)
                return {}
            async def finalize_prepared(state, lane=path, finish_lane=port.finalize):
                if state.get("preparation_error"):
                    if lane == "feed":
                        adapters[lane].reconcile_deliveries()
                    return {"result": state["preparation_error"]}
                return await finish_lane(state)
            lanes[path] = replace(port, load_candidates=use_prepared, finalize=finalize_prepared)
    async with activity_checkpointer(binding.data_directory) as saver:
        def trace_parent(event_type, name, **details):
            if attempt:
                attempt.node(event_type, lane="parent", node=name, **details)
        graph = build_autonomous_graph(lanes=lanes, load_context=load, refresh=load, finalize=finish,
            checkpointer=saver, observe=trace_parent if attempt else None, **graph_options)
        config = checkpoint_config(activity_id=run.activity_id)
        checkpoint = await graph.aget_state(config)
        if checkpoint.values and not checkpoint.next and checkpoint.values.get("result"):
            if attempt:
                attempt.emit("activity_reused", classification="success",
                    details={"status": checkpoint.values["result"].get("status")})
            return checkpoint.values["result"]
        try:
            await guard({"stage": "Resume" if checkpoint.values else "LoadContext", "identity": checkpoint.values.get("identity", identity)})
            final = await graph.ainvoke(None if checkpoint.values else {"identity": identity}, config)
        except BaseException as exc:
            ctx.db.rollback()
            status = "aborted" if isinstance(exc, ActivityScopeChangedError) else "interrupted" if not isinstance(exc, Exception) else "waiting"
            stage = None
            persisted = False
            try:
                from app.core.sqlite_concurrency import run_sqlite_session_immediate
                def save_failure_status():
                    row = ctx.db.get(ActivityGraphRun, run.activity_id, populate_existing=True)
                    if row is None:
                        raise ValueError("activity_run_missing_for_failure_status")
                    row.status = status
                    if status == "aborted":
                        row.finished_at = datetime.now(UTC)
                    row.result = {**(row.result or {}), "reason": type(exc).__name__, "stage": row.stage}
                    return row.stage
                stage = run_sqlite_session_immediate(ctx.db, save_failure_status, require_clean=True)
                persisted = True
            except Exception as persist_exc:
                ctx.db.rollback()
                import logging
                logging.getLogger(__name__).warning("activity_status_persist_failed type=%s", type(persist_exc).__name__)
            if attempt:
                attempt.emit("activity_interrupted", classification=status if persisted else "status_persist_failed",
                    details={"stage": stage, "status": status if persisted else "status_persist_failed"}, exc=exc,
                    caused_by_event_id=attempt.last_error_event_id)
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
