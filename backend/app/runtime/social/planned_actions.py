"""Execute validated social actions with durable receipts and the caller session."""

from __future__ import annotations

from app.contracts.activity_thought import ActivityThought

from app.runtime.social.subjective_composition import record_activity_thought

from app.domains.relationships.contracts.social_consumption import validate_social_context

import app.domains.social.schemas.community as social_schemas


import app.domains.social.repository.posts as social_posts_repository


import app.runtime.social.agent_tools as social_agent_tools_runtime


from app.domains.routines.policies import execution_results

from app.domains.routines.service.relationship_context import _REPLY_TARGET_ALREADY_ANSWERED

from app.domains.routines.policies import writer_tasks as writer_tasks_service

from functools import partial

from app.domains.routines.policies.action_matching import _action_name_for_policy

from app.domains.routines.policies.writer_outputs import _reply_task_results_by_id

from app.domains.routines.repository import public_action_executions as public_action_queries

from app.domains.routines.service import public_action_executions as public_action_executions

import logging


from datetime import UTC, date, datetime

from typing import Any

from sqlalchemy.exc import IntegrityError

from app.domains.routines.models.resident import AgentPublicActionExecution as _model_AgentPublicActionExecution

from app.core import unit_of_work

from app.config import settings

from app.core.redaction import redact_secret_text

from app.domains.social.contracts.subjective_context import ActionEmotionLabel, ActionMotivationKind, ActionSubjectiveContextV1

from app.runtime.social.subjective_composition import record_declared_subjective_context

from app.runtime.social import langgraph_actions as langgraph_social_apply

from app.core import prompt_safety as prompt_safety

from app.core.context_text import neutralize_context_text

from app.domains.social.contracts.feed_execution import WorldFeedContext

logger = logging.getLogger("app.services.langgraph_resident")


_PUBLIC_ACTIONS = {"post", "reply", "like", "repost", "follow", "unfollow"}


def _clip(value: Any, max_chars: int) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


_character_already_replied_to_target = social_posts_repository._character_already_replied_to_target


_brief_hash = execution_results._brief_hash


_action_signature = execution_results._action_signature


_normalize_reply_body_for_duplicate = execution_results._normalize_reply_body_for_duplicate


_skipped_public_action = execution_results._skipped_public_action


_reply_body = partial(execution_results._reply_body, reply_task_id=lambda **kwargs: _reply_task_id(**kwargs))


_reply_task_id = partial(writer_tasks_service._reply_task_id, clip=_clip)


def _reserve_public_action(
    ctx: WorldFeedContext,
    *,
    scope: str,
    action_type: str,
    target_post_id: str | None = None,
    target_profile_type: str | None = None,
    target_profile_id: str | None = None,
    brief_hash: str | None = None,
) -> tuple[_model_AgentPublicActionExecution | None, dict[str, Any] | None]:
    target_id = target_post_id or (
        f"{target_profile_type}:{target_profile_id}" if target_profile_id else None
    )
    signature = _action_signature(
        run_id=ctx.run_id,
        scope=scope,
        action_type=action_type,
        target_id=target_id,
        brief_hash=brief_hash,
    )
    existing = public_action_queries.get_public_action_execution_by_signature(
        ctx.db, signature
    )
    if existing is not None:
        if existing.status == "succeeded":
            return None, {
                "status": "reused",
                "action_type": action_type,
                "signature": signature,
                "result": existing.result or {},
            }
        return None, {
            "status": "blocked",
            "action_type": action_type,
            "signature": signature,
            "failure_class": existing.failure_class or "signature_not_retriable",
        }
    try:
        return public_action_executions.create_public_action_execution(
            ctx.db,
            run_id=ctx.run_id,
            character_id=ctx.character.id,
            signature=signature,
            scope=scope,
            action_type=action_type,
            target_post_id=target_post_id,
            target_profile_type=target_profile_type,
            target_profile_id=target_profile_id,
            brief_hash=brief_hash,
        ), None
    except IntegrityError:
        ctx.db.rollback()
        existing = public_action_queries.get_public_action_execution_by_signature(
            ctx.db, signature
        )
        return None, {
            "status": "blocked",
            "action_type": action_type,
            "signature": signature,
            "failure_class": getattr(existing, "failure_class", None)
            or "signature_race",
        }


def _finish_execution(
    ctx: WorldFeedContext,
    execution: _model_AgentPublicActionExecution,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    failure_class: str | None = None,
) -> dict[str, Any]:
    public_action_executions.mark_public_action_execution_finished(
        ctx.db,
        execution,
        status=status,
        result=result,
        failure_class=failure_class,
    )
    return {
        "status": status,
        "action_type": execution.action_type,
        "signature": execution.signature,
        "result": result or {},
        "failure_class": failure_class,
    }


def _declared_action_subjective_context(
    _action_type: str,
    plan: dict[str, Any],
) -> ActionSubjectiveContextV1 | None:
    """Convert only decision-time public fields into the persisted contract."""

    motivation_text = _clip(plan.get("motivation_text"), 280)
    raw_kind = str(plan.get("motivation_kind") or "").strip()
    if not motivation_text or not raw_kind:
        return None
    try:
        motivation_kind = ActionMotivationKind(raw_kind)
    except ValueError:
        return None
    raw_emotion = str(plan.get("emotion_label") or "unspecified").strip()
    try:
        emotion_label = ActionEmotionLabel(raw_emotion)
    except ValueError:
        emotion_label = ActionEmotionLabel.UNSPECIFIED
    emotion_text = _clip(plan.get("emotion_text"), 280) or None
    raw_intensity = plan.get("emotion_intensity")
    emotion_intensity = (
        raw_intensity
        if isinstance(raw_intensity, int) and not isinstance(raw_intensity, bool)
        else None
    )
    if emotion_label is ActionEmotionLabel.UNSPECIFIED:
        emotion_text = None
        emotion_intensity = None
    return ActionSubjectiveContextV1(
        motivation_kind=motivation_kind,
        motivation_text=motivation_text,
        emotion_label=emotion_label,
        emotion_text=emotion_text,
        emotion_intensity=emotion_intensity,
    )


def _prompt_injection_output_block(
    fields: dict[str, str],
) -> tuple[str, prompt_safety.PromptSafetyResult] | None:
    for field, text in fields.items():
        result = prompt_safety.contains_prompt_injection_output(text)
        if not result.allowed:
            return field, result
    return None


def _reply_proposal_response(
    writing: dict[str, Any], *, scope: str, index: int, post_id: str
) -> tuple[langgraph_social_apply.ProposalResponseInput | None, str | None]:
    task_id = _reply_task_id(scope=scope, index=index, post_id=post_id)
    task_result = _reply_task_results_by_id(writing).get(task_id)
    if not isinstance(task_result, dict):
        return None, None
    payload = task_result.get("proposal_response")
    if not isinstance(payload, dict):
        return None, None
    proposal_id = str(payload.get("proposal_id") or "").strip()
    decision = str(payload.get("decision") or "").strip()
    if not proposal_id or decision not in {"accept", "reject", "counter"}:
        return None, "proposal_response_invalid"
    raw_target_date = payload.get("counter_target_date")
    target_date = raw_target_date if isinstance(raw_target_date, date) else None
    if target_date is None and isinstance(raw_target_date, str) and raw_target_date:
        try:
            target_date = date.fromisoformat(raw_target_date)
        except ValueError:
            return None, "proposal_counter_date_invalid"
    return (
        langgraph_social_apply.ProposalResponseInput(
            proposal_id=proposal_id,
            decision=decision,
            counter_activity_seed=(
                str(payload.get("counter_activity_seed") or "").strip() or None
            ),
            counter_place_key=(
                str(payload.get("counter_place_key") or "").strip() or None
            ),
            counter_target_daypart=(
                str(payload.get("counter_target_daypart") or "").strip() or None
            ),
            counter_date_policy=(
                str(payload.get("counter_date_policy") or "").strip() or None
            ),
            counter_target_date=target_date,
        ),
        None,
    )


def _execute_planned_action(
    ctx: WorldFeedContext,
    *,
    action: dict[str, Any],
    scope: str,
    index: int,
    writing: dict[str, Any],
    used_reply_bodies: dict[str, str] | None = None,
) -> dict[str, Any]:
    validate_social_context(ctx)
    action_type = str(action.get("action_type") or "")
    post_id = str(action.get("post_id") or "").strip() or None
    notification_id = action.get("notification_id")
    target_type = str(action.get("target_type") or "").strip() or None
    target_id = str(action.get("target_id") or "").strip() or None
    activity_policy = getattr(ctx, "activity_policy", None)
    allowed_actions = set(getattr(activity_policy, "allowed_actions", _PUBLIC_ACTIONS))
    if _action_name_for_policy(action_type) not in allowed_actions:
        return {
            "status": "skipped",
            "action_type": action_type,
            "failure_class": "action_not_allowed",
        }
    if action_type in {"like", "repost", "reply"} and post_id is None:
        return {
            "status": "skipped",
            "action_type": action_type,
            "failure_class": "missing_post_id",
        }
    if action_type == "follow" and target_id is None and post_id is not None:
        post = social_posts_repository.get_post(ctx.db, post_id)
        if post is not None and post.author_character_id:
            target_type = "character"
            target_id = post.author_character_id
    if action_type in {"follow", "unfollow"} and (target_type != "character" or not target_id):
        return {
            "status": "skipped",
            "action_type": action_type,
            "failure_class": "missing_follow_target",
        }
    body = ""
    writer_validation: dict[str, Any] | None = None
    proposal_response_input = None
    if action_type == "reply":
        if _character_already_replied_to_target(
            ctx.db, character_id=ctx.character.id, post_id=post_id
        ):
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class=_REPLY_TARGET_ALREADY_ANSWERED,
                message="character already replied to this target post",
            )
        body, failure_class, writer_validation = _reply_body(
            writing,
            scope=scope,
            index=index,
            post_id=post_id or "",
        )
        if failure_class:
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class=failure_class,
                writer_validation=writer_validation,
            )
        proposal_response_input, proposal_failure = _reply_proposal_response(
            writing,
            scope=scope,
            index=index,
            post_id=post_id or "",
        )
        if proposal_failure:
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class=proposal_failure,
                writer_validation=writer_validation,
            )
        normalized_body = _normalize_reply_body_for_duplicate(body or "")
        if normalized_body:
            seen_reply_bodies = used_reply_bodies if used_reply_bodies is not None else {}
            previous_post_id = seen_reply_bodies.get(normalized_body)
            if previous_post_id is not None and previous_post_id != post_id:
                return _skipped_public_action(
                    action_type=action_type,
                    target_post_id=post_id,
                    failure_class="duplicate_reply_body_in_run",
                    writer_validation=writer_validation,
                )
            seen_reply_bodies[normalized_body] = post_id or ""
        blocked = _prompt_injection_output_block({"body": body})
        if blocked is not None:
            blocked_field, blocked_result = blocked
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class="prompt_injection_output_blocked",
                writer_validation=writer_validation,
                blocked_field=blocked_field,
                blocked_category=blocked_result.category,
                message="writer output was blocked before publish",
            )
    brief_hash = _brief_hash(body or action.get("brief"), notification_id)
    execution, reused = _reserve_public_action(
        ctx,
        scope=scope,
        action_type=action_type,
        target_post_id=post_id,
        target_profile_type=target_type,
        target_profile_id=target_id,
        brief_hash=brief_hash,
    )
    if reused is not None:
        if writer_validation is not None:
            reused["writer_validation"] = writer_validation
        return reused
    assert execution is not None
    try:
        if action.get("interaction_intent") == "ordinary_comment":
            execution.interaction_intent = "ordinary_comment"
            execution.comment_purpose = action.get("comment_purpose")
        occurred_at = datetime.now(UTC)
        prepared_proposal_response = None
        if proposal_response_input is not None:
            prepared_proposal_response = (
                langgraph_social_apply.prepare_proposal_response(
                    ctx.db,
                    character_id=ctx.character.id,
                    response=proposal_response_input,
                    now=occurred_at,
                )
            )
        with unit_of_work.deferred_commits():
            if action_type == "reply":
                if not body:
                    raise ValueError("reply body missing")
                result = social_agent_tools_runtime.agent_tool_actions.reply_agent_tool_post(
                    ctx.db,
                    ctx.session_key,
                    post_id or "",
                    social_schemas.TimelineReplyCreate(
                        body=body, author_character_id=ctx.character.id
                    ),
                )
                payload = {"post_id": result.id, "reply_to_post_id": post_id}
            elif action_type == "like":
                result = social_agent_tools_runtime.agent_tool_actions.like_agent_tool_post(
                    ctx.db,
                    ctx.session_key,
                    post_id or "",
                    social_schemas.PostLikeCreate(character_id=ctx.character.id),
                )
                payload = {"post_id": result.id}
            elif action_type == "repost":
                result = social_agent_tools_runtime.agent_tool_actions.repost_agent_tool_post(
                    ctx.db,
                    ctx.session_key,
                    post_id or "",
                    social_schemas.PostLikeCreate(character_id=ctx.character.id),
                )
                payload = {"post_id": result.id}
            elif action_type == "follow":
                result = social_agent_tools_runtime.agent_tool_actions.follow_agent_tool_profile(
                    ctx.db,
                    ctx.session_key,
                    social_schemas.FollowCreate(
                        target_type="character",
                        target_id=target_id or "",
                        follower_character_id=ctx.character.id,
                    ),
                )
                payload = {
                    "target_type": result.target.profile_type,
                    "target_id": result.target.id,
                }
            elif action_type == "unfollow":
                social_agent_tools_runtime.agent_tool_actions.unfollow_agent_tool_profile(
                    ctx.db,
                    ctx.session_key,
                    social_schemas.FollowCreate(
                        target_type="character",
                        target_id=target_id or "",
                        follower_character_id=ctx.character.id,
                    ),
                )
                payload = {"target_type": "character", "target_id": target_id}
            else:
                raise ValueError(f"unsupported action_type={action_type}")
            social_result = langgraph_social_apply.apply_successful_public_action(
                ctx.db,
                actor_character_id=ctx.character.id,
                action_type=action_type,
                target_post_id=post_id,
                target_character_id=target_id,
                action_result=payload,
                execution=execution,
                occurred_at=occurred_at,
                notification_id=(
                    int(notification_id) if notification_id is not None else None
                ),
                source_text=body or None,
                proposal_response=prepared_proposal_response,
            )
            action_result = _finish_execution(
                ctx, execution, status="succeeded", result=payload
            )
            if settings.ACTIVITY_THOUGHT_POLICY == "thought_v1":
                thought_value = action.get("_activity_thought")
                if action_type == "reply":
                    task_id = (writer_validation or {}).get("task_id")
                    task_result = _reply_task_results_by_id(writing).get(task_id, {})
                    thought_value = task_result.get("_activity_thought") if str(task_result.get("body") or "").strip() == body else None
                thought = ActivityThought(**thought_value) if isinstance(thought_value, dict) else ActivityThought()
                record_activity_thought(
                    ctx.db, execution=execution, event=social_result.event,
                    source_post_id=str(payload["post_id"]) if action_type == "reply" else None,
                    thought=thought, captured_at=occurred_at,
                )
            else:
                record_declared_subjective_context(
                    ctx.db,
                    execution=execution,
                    event=social_result.event,
                    source_post_id=(
                        str(payload.get("post_id"))
                        if payload.get("post_id") is not None
                        else post_id
                    ),
                    context=_declared_action_subjective_context(action_type, action),
                    captured_at=occurred_at,
                )
            ctx.db.commit()
        action_result["social_event_id"] = social_result.event.id
        if writer_validation is not None:
            action_result["writer_validation"] = writer_validation
        return action_result
    except Exception as exc:
        ctx.db.rollback()
        failure_class = type(exc).__name__
        logger.warning(
            "langgraph_public_action_failed run_id=%s character_id=%s action=%s "
            "failure_class=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            action_type,
            failure_class,
            redact_secret_text(str(exc))[:500],
        )
        action_result = _finish_execution(
            ctx,
            execution,
            status="failed",
            result=None,
            failure_class=failure_class,
        )
        if writer_validation is not None:
            action_result["writer_validation"] = writer_validation
        return action_result
