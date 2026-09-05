"""Read successful, actor-scoped posting topic keys on the caller Session."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.domains.routines.contracts.planning_context import ResidentPlanningContext
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.routines.policies.resident_clock import _today_kst_window

# Preserve the existing debug category while the runtime caller is relocated.
logger = logging.getLogger("app.services.langgraph_resident")


def _recent_independent_topic_keys(
    ctx: ResidentPlanningContext, *, limit: int = 8
) -> set[str]:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return set()
    try:
        executions = list(
            db_scalars(
                select(AgentPublicActionExecution)
                .where(AgentPublicActionExecution.character_id == ctx.character.id)
                .where(AgentPublicActionExecution.action_type == "post")
                .where(AgentPublicActionExecution.status == "succeeded")
                .order_by(
                    AgentPublicActionExecution.created_at.desc(),
                    AgentPublicActionExecution.id.desc(),
                )
                .limit(40)
            )
        )
    except Exception:
        logger.debug(
            "Failed to load recent independent topic keys",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return set()
    keys: list[str] = []
    for execution in executions:
        result = getattr(execution, "result", None)
        if not isinstance(result, dict):
            continue
        key = str(result.get("topic_key") or "").strip()
        if key and key not in keys:
            keys.append(key)
        if len(keys) >= limit:
            break
    return set(keys)


def _today_independent_topic_keys(ctx: ResidentPlanningContext) -> set[str]:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return set()
    start_utc, end_utc = _today_kst_window(ctx)
    try:
        executions = list(
            db_scalars(
                select(AgentPublicActionExecution)
                .where(AgentPublicActionExecution.character_id == ctx.character.id)
                .where(AgentPublicActionExecution.action_type == "post")
                .where(AgentPublicActionExecution.status == "succeeded")
                .where(AgentPublicActionExecution.created_at >= start_utc)
                .where(AgentPublicActionExecution.created_at <= end_utc)
                .order_by(
                    AgentPublicActionExecution.created_at.desc(),
                    AgentPublicActionExecution.id.desc(),
                )
                .limit(120)
            )
        )
    except Exception:
        logger.debug(
            "Failed to load today independent topic keys",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return set()
    keys: set[str] = set()
    for execution in executions:
        result = getattr(execution, "result", None)
        if not isinstance(result, dict):
            continue
        key = str(result.get("topic_key") or "").strip()
        if key:
            keys.add(key)
    return keys
