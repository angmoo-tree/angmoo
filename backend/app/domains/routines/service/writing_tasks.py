"""Compile selected actions into stable writer tasks with continuation context."""

from __future__ import annotations

from functools import partial
from typing import Any

from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.contracts.resident import (
    ResidentGraphState as _ResidentGraphState,
)
from app.domains.routines.contracts.resident_prompts import ResidentPromptContext
from app.domains.routines.contracts.topic_arcs import TopicArcWorkflows
from app.domains.routines.policies.resident_clock import (
    _current_kst_date,
    _format_current_time_reference,
)
from app.domains.routines.policies.writer_tasks import _post_task_id, _reply_task_id
from app.domains.routines.policies.writing_contract import (
    _POST_TEXT_WRITING_MODES,
    _coerce_action_step_count,
)
from app.domains.routines.service import topic_arcs as topic_arc_service
from app.domains.routines.service.post_writer_results import _clean_lore_chunk_ids


def _compile_write_tasks(
    ctx: ResidentPromptContext,
    action_plan: dict[str, Any],
    *,
    lore_query_result: dict[str, Any] | None = None,
    clip: ClipContextText,
    topic_workflows: TopicArcWorkflows,
) -> dict[str, Any]:
    reply_tasks: list[dict[str, Any]] = []
    if isinstance(action_plan, dict):
        for scope, key in (("feed", "feed_actions"), ("inbox", "inbox_actions")):
            actions = action_plan.get(key, [])
            if not isinstance(actions, list):
                continue
            for index, action in enumerate(actions):
                if not isinstance(action, dict) or action.get("action_type") != "reply":
                    continue
                post_id = str(action.get("post_id") or "").strip()
                if not post_id:
                    continue
                reply_tasks.append(
                    {
                        "task_id": _reply_task_id(
                            scope=scope, index=index, post_id=post_id, clip=clip
                        ),
                        "scope": scope,
                        "action_index": index,
                        "target_post_id": post_id,
                        "notification_id": action.get("notification_id"),
                        "notification_type": action.get("notification_type"),
                        "activity_proposal": action.get("activity_proposal"),
                        "brief": clip(action.get("brief"), 600) or None,
                        "conversation_judgment": action.get("conversation_judgment"),
                        "conversation_reason": clip(
                            action.get("conversation_reason"), 500
                        )
                        or None,
                    }
                )
    writing = action_plan.get("writing") if isinstance(action_plan, dict) else None
    post_task = None
    if isinstance(writing, dict) and writing.get("mode") in _POST_TEXT_WRITING_MODES:
        post_task = {
            "task_id": _post_task_id(
                ctx,
                writing,
                clip=clip,
                coerce_topic_arc=partial(
                    topic_arc_service._coerce_topic_arc_payload,
                    workflows=topic_workflows,
                ),
            ),
            "mode": writing.get("mode"),
            "source_post_id": writing.get("source_post_id"),
            "topic_key": writing.get("topic_key"),
            "feed_cue_id": writing.get("feed_cue_id"),
            "relationship_point_id": writing.get("relationship_point_id"),
            "source_mix": writing.get("source_mix") or "none",
            "mention_required": bool(writing.get("mention_required")),
            "mention_target_handle": writing.get("mention_target_handle"),
            "mention_target_character_id": writing.get("mention_target_character_id"),
            "selected_feed_seed": writing.get("selected_feed_seed"),
            "writing_form": writing.get("writing_form") or "thought",
            "action_step_count": _coerce_action_step_count(
                writing.get("action_step_count")
            ),
            "source_body": clip(writing.get("source_body"), 1000) or None,
            "brief": clip(writing.get("brief"), 800) or None,
            "current_time_reference": _format_current_time_reference(
                ctx.run_started_at
            ),
        }
        topic_arc = topic_arc_service._coerce_topic_arc_payload(
            writing.get("topic_arc"), workflows=topic_workflows
        )
        active_step = topic_arc_service._topic_arc_active_step(
            topic_arc or {}, workflows=topic_workflows
        )
        if topic_arc and active_step:
            carryover_time_context = writing.get("carryover_time_context")
            if not isinstance(carryover_time_context, dict):
                carryover_time_context = topic_arc_service._carryover_time_context(
                    active_step,
                    topic_arc,
                    _current_kst_date(ctx),
                    workflows=topic_workflows,
                )
            topic_arc_for_prompt = dict(topic_arc)
            topic_arc_for_prompt["carryover_time_context"] = carryover_time_context
            post_task["topic_arc"] = topic_arc_service._topic_arc_for_prompt(
                topic_arc_for_prompt, workflows=topic_workflows
            )
            post_task["active_step"] = active_step
            post_task["carryover_time_context"] = carryover_time_context
            post_task["completed_step_summaries"] = (
                topic_arc_service._topic_arc_completed_step_summaries(
                    topic_arc, workflows=topic_workflows
                )
            )
            post_task["arc_continuity_context"] = (
                topic_arc_service._topic_arc_continuity_context(
                    ctx, topic_arc, workflows=topic_workflows
                )
            )
        if writing.get("mode") == "independent" and isinstance(lore_query_result, dict):
            lore_query_mode = str(
                lore_query_result.get("lore_query_mode") or ""
            ).strip()
            retrieval_mode = str(lore_query_result.get("retrieval_mode") or "").strip()
            lore_chunk_ids = _clean_lore_chunk_ids(
                lore_query_result.get("lore_chunk_ids"), clip=clip
            )
            if lore_query_mode:
                post_task["lore_query_mode"] = lore_query_mode
            if retrieval_mode:
                post_task["retrieval_mode"] = retrieval_mode
            if lore_chunk_ids:
                post_task["lore_chunk_ids"] = lore_chunk_ids
            lore_context = str(lore_query_result.get("lore_context") or "").strip()
            if lore_context:
                post_task["lore_context"] = lore_context
    return {"reply_tasks": reply_tasks, "post_task": post_task}
