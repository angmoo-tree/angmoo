"""Execute a frozen V2 claim with inherited durable child checkpoints."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from app.core.activity_transactions import activity_write

from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
from app.domains.worlds.models import World, WorldMembership
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.binding import current, observer
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
from app.runtime.autonomous_activity.contracts import ActivityIdentity
from app.runtime.autonomous_activity.graph import build_autonomous_graph
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.output_recovery import MAX_CALL_BUDGET
from app.runtime.autonomous_activity.social_lane import plain
from app.runtime.character_activity_state import initialize_from_last_success


class ActivityScopeChangedError(ValueError):
    pass


def context_for_activity_run(ctx, run):
    if run.activity_id == ctx.run_id:
        return ctx
    # The recovery lease belongs to a fresh run. Model/persona effects continue
    # to use the original activity's accepted inputs and canonical effect ID.
    from app.domains.routines.models import AgentRun
    original_run = ctx.db.get(AgentRun, run.activity_id)
    snapshot = getattr(original_run, "input_snapshot", None)
    stored_configuration = (run.result or {}).get("_world_configuration")
    if stored_configuration is not None:
        snapshot = {**(snapshot or {}), "_world_configuration": stored_configuration}
    return replace(ctx, run_id=run.activity_id, input_snapshot=snapshot)


async def run_personalized_activity(ctx, *, actor, run, action_executor=None):
    from app.domains.world_characters.contracts.checkpoint_retention import (
        TERMINAL_STATUSES, business_result, completion,
    )
    latest = ctx.db.get(ActivityGraphRun, run.activity_id, populate_existing=True)
    if latest is not None and latest.status in TERMINAL_STATUSES:
        current_actor = ctx.db.get(WorldCharacter, actor.id, populate_existing=True)
        member = ctx.db.get(WorldMembership, current_actor.membership_id, populate_existing=True) if current_actor else None
        world = ctx.db.get(World, latest.world_id, populate_existing=True)
        from app.domains.characters.models import Character
        character = ctx.db.get(Character, ctx.character.id, populate_existing=True)
        if (current_actor is None or current_actor.character_id != ctx.character.id
                or current_actor.world_id != latest.world_id or world is None
                or character is None or character.owner_id != ctx.user_id
                or (latest.world_id, latest.world_character_id) != (actor.world_id, actor.id)
                or member is None or member.world_id != actor.world_id
                or member.user_id != ctx.user_id or member.status != "active"
                or latest.engine != run.engine or latest.contract_version != run.contract_version):
            raise ActivityScopeChangedError("activity_completed_scope_invalid")
        completion(latest)
        from app.runtime.autonomous_activity.checkpoint_maintenance import validate_completion_receipts
        validate_completion_receipts(ctx.db, latest)
        return business_result(latest.result)
    from app.domains.world_characters.contracts.activity_retirement import retired_identity
    if retired_identity(run.engine, run.contract_version):
        from app.domains.characters.models import Character
        from app.runtime.autonomous_activity.retirement import transition_uow
        character = ctx.db.get(Character, actor.character_id)
        if (latest is None or character is None or character.owner_id != ctx.user_id
                or (latest.world_id, latest.world_character_id) != (actor.world_id, actor.id)):
            raise ActivityScopeChangedError("legacy_activity_scope_invalid")
        actor_id, activity_id, old_engine, old_version = actor.id, run.activity_id, run.engine, run.contract_version
        ctx.db.commit()
        outcome = transition_uow(ctx.db, actor_id=actor_id, entry_run_id=ctx.run_id)
        row = ctx.db.get(ActivityGraphRun, activity_id, populate_existing=True)
        return {"engine": old_engine, "contract_version": old_version,
            "status": row.status if row.status == "abandoned" else "aborted",
            "reason": outcome.reason or "legacy_sns_abandoned", "publish_result": {"public_action_count": 0},
            "llm_usage_summary": {"call_count": 0}}
    binding = current()
    if binding is None:
        raise RuntimeError("personalized_activity_runtime_unavailable")
    lease_run_id = ctx.run_id
    ctx = context_for_activity_run(ctx, run)
    # Diagnostics are optional and cannot hold the activity's execution lease.
    try:
        sink = observer()
        attempt = sink.begin(activity_id=run.activity_id, agent_run_id=lease_run_id,
            world_id=actor.world_id, actor_id=actor.id, activity_started_at=run.started_at) if sink else None
    except Exception:
        attempt = None
    # Normal and recovery ceilings remain independent of eligible node count.
    tracker = RunLlmTracker(max_calls=MAX_CALL_BUDGET, observer=attempt.tracker_event if attempt else None)
    identity = ActivityIdentity(activity_id=run.activity_id, world_id=actor.world_id, actor_id=actor.id,
        contract_version=run.contract_version,
        cause="manual" if "manual" in ctx.session_key else "scheduled", generation_model=ctx.generation_model, thinking_level=ctx.generation_thinking_level).model_dump()
    policy = (run.result or {}).get("routine_policy")
    from app.domains.world_characters.contracts.social_io import read_policies
    execution_policies = read_policies(run.result).model_dump()
    identity.update(execution_policies)
    from app.contracts.sns_generation import read_generation_policies
    generation_policies = read_generation_policies(run.result).model_dump()
    identity.update(generation_policies)
    from app.domains.relationships.contracts.social_context import read_currentness_policy, CURRENTNESS_POLICY_KEY
    relationship_policy = read_currentness_policy(run.result)
    identity[CURRENTNESS_POLICY_KEY] = relationship_policy
    from app.contracts.relationship_currentness import EFFECT_PROGRESS_KEY, EFFECT_PROGRESS_REVISION
    from app.contracts.activity_cancellation import RECOVERY_POLICY_KEY, RECOVERY_REVISION
    recovery_policy = (run.result or {}).get(RECOVERY_POLICY_KEY)
    if recovery_policy not in {None, RECOVERY_REVISION}:
        raise ActivityScopeChangedError("activity_recovery_policy_invalid")
    if recovery_policy is not None:
        identity[RECOVERY_POLICY_KEY] = recovery_policy
    effect_policy = (run.result or {}).get(EFFECT_PROGRESS_KEY)
    if effect_policy not in {None, EFFECT_PROGRESS_REVISION}:
        raise ActivityScopeChangedError("relationship_effect_policy_invalid")
    if effect_policy is not None:
        identity[EFFECT_PROGRESS_KEY] = effect_policy
    from app.contracts.name_binding import read_name_binding
    from app.domains.world_characters.service.name_binding import validate_name_binding
    name_binding = read_name_binding(run.result)
    frozen_names = (run.result or {}).get("name_binding")
    name_policy = (run.result or {}).get("name_binding_policy")
    from app.runtime.autonomous_activity.configuration import configuration_for_activity, accepted_autonomy
    configuration = configuration_for_activity(ctx, actor)
    frozen_configuration = configuration.request_snapshot() if configuration is not None else None
    from app.contracts.environment import EnvironmentSnapshot
    environment = EnvironmentSnapshot.from_dict((run.result or {}).get("environment_snapshot"))
    if policy is not None:
        identity.update(routine_output_contract=policy["output_contract"], routine_state_schema_version=policy["state_schema_version"], routine_thought_policy=policy["thought_policy"])
    if attempt:
        attempt.emit("activity_identity", details={
            "cause": identity["cause"], "contract_version": identity["contract_version"],
            "generation_model": identity["generation_model"],
            "thinking_level": identity["thinking_level"], "routine_output_contract": identity["routine_output_contract"],
            "routine_state_schema_version": identity["routine_state_schema_version"], "routine_thought_policy": identity["routine_thought_policy"]})

    def validate_claim(local_ctx=None, local_actor=None):
        """Read-only claim fence; also runs inside each fresh writer boundary."""
        return validate_context_claim(local_ctx or ctx, local_actor or actor)

    # DB stages must validate with their own Session, never the parent closure.
    validate_claim.bind_context = lambda local_ctx, local_actor: lambda: validate_context_claim(local_ctx, local_actor)

    def validate_context_claim(ctx, actor):
        from app.runtime.autonomous_activity.llm_context import world_material
        world_material(ctx)
        active = ctx.db.get(CharacterActiveWorld, ctx.character.id, populate_existing=True)
        current_actor = ctx.db.get(WorldCharacter, actor.id, populate_existing=True)
        world = ctx.db.get(World, actor.world_id, populate_existing=True)
        membership = ctx.db.get(WorldMembership, actor.membership_id, populate_existing=True)
        if (active is None or active.world_character_id != actor.id or current_actor is None
            or current_actor.world_id != identity["world_id"] or current_actor.control_mode != "autonomous"
            or current_actor.status != "active" or not accepted_autonomy(ctx, current_actor)
            or world is None or world.status != "published" or world.readiness_status != "publish_ready"
            or membership is None or membership.status != "active" or membership.user_id != ctx.user_id):
            raise ActivityScopeChangedError("activity_scope_changed")
        row = ctx.db.get(ActivityGraphRun, identity["activity_id"], populate_existing=True)
        if row is not None and row.status in TERMINAL_STATUSES:
            raise ActivityScopeChangedError("activity_already_completed")
        if (row is None or row.engine != "personalized_graph_v2" or row.contract_version != identity["contract_version"]
                or (row.world_id, row.world_character_id) != (actor.world_id, actor.id)):
            raise ActivityScopeChangedError("activity_contract_changed")
        if (row.result or {}).get("routine_policy") != policy:
            raise ActivityScopeChangedError("routine_policy_changed")
        if read_policies(row.result).model_dump() != execution_policies:
            raise ActivityScopeChangedError("social_execution_policy_changed")
        if read_generation_policies(row.result).model_dump() != generation_policies:
            raise ActivityScopeChangedError("activity_generation_policy_changed")
        if (row.result or {}).get(RECOVERY_POLICY_KEY) != recovery_policy:
            raise ActivityScopeChangedError("activity_recovery_policy_changed")
        if (row.result or {}).get(EFFECT_PROGRESS_KEY) != effect_policy:
            raise ActivityScopeChangedError("relationship_effect_policy_changed")
        if read_currentness_policy(row.result) != relationship_policy:
            raise ActivityScopeChangedError("relationship_validation_policy_changed")
        if (row.result or {}).get("name_binding") != frozen_names:
            raise ActivityScopeChangedError("name_binding_changed")
        if (row.result or {}).get("name_binding_policy") != name_policy:
            raise ActivityScopeChangedError("name_binding_changed")
        if (row.result or {}).get("_world_configuration") != frozen_configuration:
            raise ActivityScopeChangedError("world_configuration_changed")
        if name_binding is not None:
            validate_name_binding(ctx.db, name_binding, actor=current_actor, owner_id=ctx.user_id)
        from app.domains.routines.models import AgentRun, AgentSlot
        from app.domains.world_characters.service.activity_state import utc
        slot = ctx.db.get(AgentSlot, ctx.agent_id, populate_existing=True)
        canonical = ctx.db.get(AgentRun, lease_run_id, populate_existing=True)
        now = datetime.now(UTC)
        if (slot is None or canonical is None or canonical.status != "running"
            or canonical.user_id != ctx.user_id or canonical.character_id != ctx.character.id or canonical.agent_id != ctx.agent_id
            or slot.locked_by_run_id != lease_run_id or slot.assigned_character_id != ctx.character.id
            or slot.assigned_user_id != ctx.user_id or slot.lease_expires_at is None
            or utc(slot.lease_expires_at) <= now):
            raise ActivityScopeChangedError("activity_claim_lost")
        return row, slot, now

    async def guard(state):
        stored_identity = state.get("identity", identity)
        if any(stored_identity.get(key) != identity.get(key) for key in ("activity_id", "contract_version", "world_id", "actor_id", "generation_model", "thinking_level", "routine_output_contract", "routine_state_schema_version", "routine_thought_policy")):
            raise ActivityScopeChangedError("activity_identity_or_model_changed")
        if read_policies(stored_identity).model_dump() != execution_policies:
            raise ActivityScopeChangedError("social_execution_policy_changed")
        if read_generation_policies(stored_identity).model_dump() != generation_policies:
            raise ActivityScopeChangedError("activity_generation_policy_changed")
        if stored_identity.get(RECOVERY_POLICY_KEY) != recovery_policy:
            raise ActivityScopeChangedError("activity_recovery_policy_changed")
        if stored_identity.get(EFFECT_PROGRESS_KEY) != effect_policy:
            raise ActivityScopeChangedError("relationship_effect_policy_changed")
        if read_currentness_policy(stored_identity) != relationship_policy:
            raise ActivityScopeChangedError("relationship_validation_policy_changed")
        from app.runtime.autonomous_activity.db_stage import run_context_db_stage
        await run_context_db_stage(ctx, actor,
            lambda local_ctx, local_actor: activity_write(local_ctx.db,
                lambda: renew_claim(state, local_ctx, local_actor)))
        return {}

    def renew_claim(state, ctx, actor):
        ctx.db.expire_all()
        row, slot, now = validate_claim(ctx, actor)
        if state.get("stage") in {"ActionPlanner", "DecisionDraft", "ValidateDecision", "Writer", "ValidateDraft", "Execute"}:
            from app.domains.world_characters.service.activity_state import read_state
            from app.runtime.autonomous_activity.revalidation import assert_memories_current
            from app.runtime.autonomous_activity.committed_resume import settlement, committed_executions
            adapter = adapters.get(state.get("_lane"))
            if adapter is not None:
                from copy import copy
                adapter = copy(adapter)
                adapter.ctx, adapter.actor = ctx, actor
            confirmed = settlement(adapter, state, state["_lane"]) if adapter is not None else None
            completed = (adapter is not None and confirmed is not None
                and committed_executions(adapter, state, state["_lane"]) is not None)
            if not completed and any(value.get("packets") and target not in state.get("memory_validations", {})
                   for target, value in state.get("memories", {}).items()):
                raise ActivityScopeChangedError("activity_memory_validation_unavailable")
            if not completed:
                assert_memories_current(ctx.db, owner_id=ctx.user_id, world_id=actor.world_id, actor_id=actor.id,
                    memories=state.get("memories", {}), validations=state.get("memory_validations", {}))
            # Current state is reference input. Settlement retains its CAS and
            # cannot overwrite a concurrent state update with this old proposal.
        slot.lease_expires_at = now + timedelta(minutes=10)
        completed_paths = {path: state[f"{path}_result"] for path in ("inbox", "routine", "feed") if f"{path}_result" in state}
        if completed_paths:
            row.result = {**(row.result or {}), "paths": {**(row.result or {}).get("paths", {}), **completed_paths}}
        row.status = "running"
        row.result = {**(row.result or {}), "contract_version": identity["contract_version"]}
        row.stage = state.get("stage", "LoadContext")

    preparation_status = {}

    async def load(state):
        await guard(state)
        if state.get("shared_context"):
            shared = state["shared_context"]
            if shared.get("world_id") != actor.world_id or shared.get("actor_id") != actor.id:
                raise ActivityScopeChangedError("activity_initial_input_scope_invalid")
            return {"shared_context": shared}
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
        activity_write(ctx.db, lambda: initialize_from_last_success(ctx.db, actor=actor))
        search_settings = (False, False)
        if binding.prepare_search is not None:
            from app.runtime.memory.composition import search_preparation_settings
            search_settings = search_preparation_settings(ctx.db, ctx.user_id, actor.world_id, actor.id)
        ctx.db.commit()
        if search_settings[0]:
            binding.prepare_search(semantic=search_settings[1])
        shared = plain(shared_input(ctx, actor, ctx.db.get(World, actor.world_id), environment=environment))
        if attempt and name_binding is not None:
            attempt.emit("name_binding", details={"policy_version": name_binding.policy_version,
                "binding_digest": name_binding.digest, "profile_version": name_binding.user_profile_version,
                "fields": shared["persona"]["name_binding"]["fields"]})
        return {"shared_context": shared}

    async def finish(state):
        results = {path: state.get(f"{path}_result", {}) for path in ("inbox", "routine", "feed")}
        count = sum(r.get("public_action_count", 0) for r in results.values())
        result = {"engine": "personalized_graph_v2", "contract_version": identity["contract_version"],
            "execution_order": ["inbox", "feed", "routine"],
            "status": "failed" if any(r.get("status") == "failed" for r in results.values()) else "completed" if count else "observed",
            "summary": "Personalized Inbox, Routine and Feed graph completed.",
            "publish_result": {"public_action_count": count}, "paths": results,
            "llm_usage_summary": tracker.summary(), "llm_rate_limit_waits": tracker.rate_limit_waits,
            "daily_preparation": preparation_status}
        def save_result():
            row, _, _ = validate_claim()
            previous = {key: value for key, value in (row.result or {}).items()
                if key not in {"reason", "stage", "storage_sqlstate"}}
            merged = {**previous, **result}
            row.status, row.stage, row.result, row.finished_at = merged["status"], "Finalize", plain(merged), datetime.now(UTC)
            if row.status in TERMINAL_STATUSES:
                completion(row)
            return merged
        result = activity_write(ctx.db, save_result)
        if attempt:
            attempt.emit("activity_result", classification=result["status"], details={
                "status": result["status"], "public_action_count": count,
                "paths": {path: {"status": item.get("status"),
                    "public_action_count": item.get("public_action_count", 0)} for path, item in results.items()}})
        return {"result": result}

    from app.runtime.autonomous_activity.combined_lanes import CombinedInboxLane, CombinedFeedLane, CombinedRoutineLane
    from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
    classes = (("inbox", CombinedInboxLane), ("routine", CombinedRoutineLane), ("feed", CombinedFeedLane))
    from app.runtime.autonomous_activity.input_budget import SnsInputBudget
    budget = SnsInputBudget(ctx.db, run.activity_id, notify=tracker._notify) if generation_policies["sns_input_budget_policy"] else None
    version_options = {"ledger": RecoveryLedger(ctx.db, run.activity_id), "policies": {**execution_policies, **generation_policies,
        "_situation_policy": (run.result or {}).get("_situation_policy")}, "input_budget": budget}
    adapters = {path: cls(ctx, actor=actor, tracker=tracker, hybrid_service=binding.hybrid_service,
                      guard=guard, claim_validator=validate_claim,
                      **version_options,
                      **({"lane": path, "action_executor": action_executor} if path != "routine" else {}))
        for path, cls in classes}
    lanes = {path: adapter.ports() for path, adapter in adapters.items()}
    for path, port in list(lanes.items()):
        def failed_sync(exc, lane):
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
            feed_stale = identity["contract_version"] == 2 and lane == "feed" and reason in {
                "feed_target_stale", "activity_source_changed", "activity_target_unavailable", "feed_affordance_changed", "feed_claim_changed"}
            from app.runtime.autonomous_activity.inputs import relationship_failure_details, stale_relationship_input
            validation_details = relationship_failure_details(exc)
            relationship_stale = identity["contract_version"] == 2 and stale_relationship_input(exc, lane=lane, stage=row.stage)
            stale = feed_stale or relationship_stale
            return {"path": lane, "status": "no_action" if stale else "failed", "reason": reason,
                "failed_stage": row.stage, "public_action_count": 0,
                **({"policy_outcome": "input_changed_before_publication"} if relationship_stale else {}),
                **({"relationship_validation": validation_details} if validation_details is not None else {}),
                **({"feed_summary": adapters[lane].finalize_unavailable(reason)} if stale and lane == "feed" else {})}
        async def failed(exc, lane=path, operation=failed_sync):
            from app.core.async_session import session_call
            return await session_call(ctx.db, lambda: operation(exc, lane))
        def trace(event_type, name, *, path=path, **details):
            if attempt:
                attempt.node(event_type, lane=path, node=name, **details)
        async def record_observed_failure(state, exc, lane=path):
            from app.runtime.autonomous_activity.experience_failures import record_failure
            from app.runtime.autonomous_activity.db_stage import run_context_db_stage
            if str(exc) not in {"feed_target_stale", "activity_source_changed", "activity_target_unavailable", "feed_affordance_changed", "feed_claim_changed"}:
                return
            def save(local_ctx, local_actor):
                return activity_write(local_ctx.db, lambda: record_failure(local_ctx.db, lane, state, str(exc)))
            await run_context_db_stage(ctx, actor, save)
        lanes[path] = replace(port, on_error=failed, observe=trace, record_observed_failure=record_observed_failure)
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
            return business_result(checkpoint.values["result"])
        try:
            await guard({"stage": "Resume" if checkpoint.values else "LoadContext", "identity": checkpoint.values.get("identity", identity)})
            final = await graph.ainvoke(None if checkpoint.values else {"identity": identity}, config)
        except BaseException as exc:
            ctx.db.rollback()
            import asyncio
            if isinstance(exc, asyncio.CancelledError):
                # Resident cancellation owns one atomic AgentRun/slot/graph cleanup.
                # A failed cleanup is recovered from the expired canonical lease.
                if attempt:
                    from app.contracts.activity_cancellation import cancellation_reason
                    attempt.emit("activity_interrupted", classification="interrupted",
                        details={"reason":str(cancellation_reason())}, exc=exc)
                raise
            status = "aborted" if isinstance(exc, ActivityScopeChangedError) else "interrupted" if not isinstance(exc, Exception) else "waiting"
            stage = None
            persisted = False
            try:
                def save_failure_status():
                    row = ctx.db.get(ActivityGraphRun, run.activity_id, populate_existing=True)
                    if row is None:
                        raise ValueError("activity_run_missing_for_failure_status")
                    if row.status in TERMINAL_STATUSES:
                        # Finalize committed before the last SDK checkpoint write.
                        # Its durable completion must survive checkpoint I/O failure.
                        completion(row)
                        return row.stage, row.status
                    row.status = status
                    if status == "aborted":
                        row.finished_at = datetime.now(UTC)
                    from app.core.postgresql_concurrency import sqlstate
                    row.result = {**(row.result or {}), "reason": type(exc).__name__, "stage": row.stage,
                        "storage_sqlstate": sqlstate(exc)}
                    return row.stage, row.status
                stage, status = activity_write(ctx.db, save_failure_status, require_clean=True)
                persisted = True
            except Exception as persist_exc:
                ctx.db.rollback()
                import logging
                logging.getLogger(__name__).warning("activity_status_persist_failed type=%s", type(persist_exc).__name__)
            if attempt:
                attempt.emit("activity_checkpoint_write_failed" if status in TERMINAL_STATUSES else "activity_interrupted", classification=status if persisted else "status_persist_failed",
                    details={"stage": stage, "status": status if persisted else "status_persist_failed"}, exc=exc,
                    caused_by_event_id=attempt.last_error_event_id)
            raise
        from app.domains.world_characters.service.checkpoint_retention import confirm_graph
        try:
            terminal_snapshot = await graph.aget_state(config)
            if (terminal_snapshot.next or terminal_snapshot.tasks
                    or not terminal_snapshot.values.get("result")
                    or business_result(terminal_snapshot.values["result"]) != business_result(final["result"])):
                raise ValueError("activity_final_checkpoint_unconfirmed")
            def confirm():
                completed = ctx.db.get(ActivityGraphRun, run.activity_id, populate_existing=True)
                confirm_graph(ctx.db, completed)
            activity_write(ctx.db, confirm)
        except Exception:
            ctx.db.rollback()
            import logging
            logging.getLogger(__name__).warning("activity_checkpoint_confirmation_deferred")
        return business_result(final["result"])
