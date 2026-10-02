"""Manual and scheduled SNS enter the supported V2 graph through one boundary."""
import asyncio

from sqlalchemy import select

from app.config import settings
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.activity_retirement import retired_identity
from app.domains.world_characters.service.activity_engines import bind_run
from app.runtime.routines import activity_policy as agent_activity_policy
from app.runtime.routine_posts.sqlalchemy_runtime import routine_world_character_for_character
from app.runtime.social.planned_actions import _execute_planned_action
from app.runtime.autonomous_activity.retirement import transition_uow

_GRAPH_SEMAPHORE = asyncio.Semaphore(settings.langgraph_max_concurrent_graphs)


def _blocked(reason, *, status="aborted"):
    return {"engine": "personalized_graph_v2", "status": status, "reason": reason,
            "summary": "SNS execution needs settlement or preparation before a new activity.",
            "publish_result": {"public_action_count": 0},
            "llm_usage_summary": {"call_count": 0, "provider_call_count": 0}}


def _bind_activity_run(ctx, actor):
    existing = ctx.db.get(ActivityGraphRun, ctx.run_id, populate_existing=True)
    if existing is not None and retired_identity(existing.engine, existing.contract_version):
        return existing
    row = ctx.db.scalar(select(ActivityGraphRun).where(
        ActivityGraphRun.world_character_id == actor.id, ActivityGraphRun.world_id == actor.world_id,
        ActivityGraphRun.engine == "personalized_graph_v2", ActivityGraphRun.contract_version == 2,
        ActivityGraphRun.status.in_(("running", "waiting", "interrupted")),
    ).order_by(ActivityGraphRun.started_at).limit(1))
    if row is None:
        row = bind_run(ctx.db, actor=actor, activity_id=ctx.run_id)
    ctx.db.commit()
    return row


async def run_social_activity(ctx):
    actor = routine_world_character_for_character(ctx.db, character_id=ctx.character.id)
    if actor is None:
        return _blocked("autonomous_world_character_required")
    from app.domains.world_characters.contracts.checkpoint_retention import TERMINAL_STATUSES
    from app.runtime.autonomous_activity.execution import run_personalized_activity
    existing = ctx.db.get(ActivityGraphRun, ctx.run_id, populate_existing=True)
    if existing is not None and existing.status in TERMINAL_STATUSES:
        # The canonical reader owns authorization and receipt validation. A
        # completed ID never starts conversion, binds another unfinished ID,
        # acquires runtime dependencies or submits a new generation request.
        return await run_personalized_activity(ctx, actor=actor, run=existing)
    if agent_activity_policy.is_imported_world_runtime_locked(ctx.db, actor):
        return {**_blocked("AUTONOMY_DISABLED", status="observed"), "outcome": "AUTONOMY_DISABLED"}
    async with _GRAPH_SEMAPHORE:
        actor_id = actor.id
        ctx.db.commit()
        transition = transition_uow(ctx.db, actor_id=actor_id, entry_run_id=ctx.run_id)
        if transition.state != "ready":
            return _blocked(transition.reason or "legacy_engine_transition_required")
        actor = ctx.db.get(type(actor), actor_id, populate_existing=True)
        activity = _bind_activity_run(ctx, actor)
        if retired_identity(activity.engine, activity.contract_version):
            return _blocked("legacy_sns_abandoned")
        return await run_personalized_activity(ctx, actor=actor, run=activity,
                                               action_executor=_execute_planned_action)
