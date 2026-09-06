"""Temporary existing Memory action persistence until the signed B7 merge."""
from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.models.agent_runs import AgentDaypartMemoryEvent

def _record_daypart_action_memory(
    db: Session, *, run: models.AgentRun, action_memory: dict[str, Any]
) -> None:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    session_context = gateway_result.get("session_context")
    if not isinstance(session_context, dict) or not session_context.get("daypart_persistent"):
        return
    memory_session_key = session_context.get("memory_session_key")
    daypart_start_date = session_context.get("daypart_start_date")
    activity_daypart = session_context.get("activity_daypart")
    if not (
        isinstance(memory_session_key, str)
        and isinstance(daypart_start_date, str)
        and isinstance(activity_daypart, str)
    ):
        return
    try:
        parsed_daypart_start = datetime.fromisoformat(daypart_start_date).date()
    except ValueError:
        return
    event = AgentDaypartMemoryEvent(
        character_id=run.character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=parsed_daypart_start,
        activity_daypart=activity_daypart,
        event_type=f"action_{action_memory.get('action_type') or 'public'}",
        source_post_id=action_memory.get("source_post") or action_memory.get("post_id"),
        run_id=run.id,
        summary=str(action_memory.get("public_result_summary") or "")[:2000],
        payload=action_memory,
        topic_signature=str(action_memory.get("topic") or "")[:300] or None,
    )
    db.add(event)
    db.commit()
