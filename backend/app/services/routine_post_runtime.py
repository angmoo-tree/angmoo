from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core import unit_of_work
from app.cruds import agent_runs as agent_run_crud
from app.services import (
    activity_runtime,
    agent_activity_policy,
    joint_activity_runtime,
    social_event_runtime,
)
from app.services import community as community_service
from app.services.direct_llm import (
    DirectLlmDeferred,
    DirectLlmError,
    DirectLlmJsonError,
    RunLlmTracker,
)
from app.services.resident_contracts import LangGraphResidentContext
from app.services.routine_post_context import (
    RoutineContextUnavailable,
    RoutineInteractionSource,
    assemble_routine_post_context,
)
from app.services.routine_post_planner import (
    ROUTINE_CONTRACT_VERSION,
    DirectRoutinePostProvider,
    RoutineGeneration,
    RoutinePostProvider,
    validate_routine_generation,
)


logger = logging.getLogger(__name__)
CLAIM_LEASE = timedelta(minutes=10)


def routine_world_character_for_character(
    db: Session, *, character_id: str
) -> models.WorldCharacter | None:
    active_world = db.get(models.CharacterActiveWorld, character_id)
    if active_world is None:
        return None
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if (
        world_character is None
        or world_character.character_id != character_id
        or world_character.activity_runtime_mode != "routine_resident_v1"
    ):
        return None
    return world_character


def _safe_result(
    *,
    outcome: str,
    tracker: RunLlmTracker | None = None,
    status: str = "observed",
    failure_class: str | None = None,
) -> dict[str, object]:
    return {
        "engine": "routine_resident_v1",
        "status": status,
        "summary": f"Routine resident outcome: {outcome}.",
        "routine_outcome": outcome,
        "failure_class": failure_class,
        "publish_result": {"public_action_count": 0},
        "llm_usage_summary": (tracker or RunLlmTracker(max_calls=3)).summary(),
    }


def _beat_idempotency_key(
    *, world_character_id: str, episode_id: str, scheduled_for: datetime
) -> str:
    value = "|".join(
        (
            world_character_id,
            episode_id,
            scheduled_for.astimezone(UTC).isoformat(),
            ROUTINE_CONTRACT_VERSION,
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()


def _execution_signature(*, world_character_id: str, beat_id: str) -> str:
    value = "|".join(
        (
            world_character_id,
            beat_id,
            "post",
            ROUTINE_CONTRACT_VERSION,
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()


def _planner_hash(generation: RoutineGeneration) -> str:
    payload = generation.plan.model_dump(mode="json")
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _retryable_provider_error(exc: BaseException) -> bool:
    if isinstance(exc, DirectLlmDeferred):
        return True
    value = f"{type(exc).__name__}:{exc}".lower()
    return any(
        marker in value
        for marker in ("timeout", "temporar", "rate", "429", "500", "502", "503", "504")
    )


def _failure_code(exc: BaseException) -> str:
    if isinstance(exc, DirectLlmJsonError):
        return "provider_response_invalid"
    if isinstance(exc, DirectLlmDeferred):
        return "provider_deferred"
    if _retryable_provider_error(exc):
        return "provider_transient"
    if isinstance(exc, DirectLlmError):
        return "provider_failed"
    return "routine_generation_failed"


def _runtime_error_code(exc: activity_runtime.ActivityRuntimeError) -> str:
    value = str(exc).strip()
    return value.upper() if value else "ROUTINE_RUNTIME_CONFLICT"


def _finish_failed_beat(
    db: Session,
    *,
    beat: models.ActivityBeat,
    claim_run_id: str,
    reason_code: str,
    retryable: bool,
) -> None:
    try:
        if retryable and beat.attempt_count < 2:
            activity_runtime.release_activity_beat_for_retry(
                db,
                beat_id=beat.id,
                claim_run_id=claim_run_id,
                reason_code=reason_code,
            )
        else:
            activity_runtime.fail_activity_beat(
                db,
                beat_id=beat.id,
                claim_run_id=claim_run_id,
                reason_code=reason_code,
            )
    except activity_runtime.ActivityRuntimeError:
        db.rollback()
        logger.exception(
            "routine_beat_failure_finalize_failed beat_id=%s run_id=%s",
            beat.id,
            claim_run_id,
        )


async def run_routine_post_runtime(
    resident_context: LangGraphResidentContext,
    *,
    interaction_source: RoutineInteractionSource | None = None,
    provider: RoutinePostProvider | None = None,
) -> dict[str, object]:
    db = resident_context.db
    tracker = RunLlmTracker(max_calls=3)
    world_character = routine_world_character_for_character(
        db, character_id=resident_context.character.id
    )
    if world_character is None:
        return _safe_result(outcome="NO_ROUTINE_CONTEXT", tracker=tracker)
    manual = agent_activity_policy.is_manual_policy_session(
        resident_context.session_key
    )
    if not world_character.autonomous_enabled and not manual:
        return _safe_result(outcome="AUTONOMY_DISABLED", tracker=tracker)
    if "post" not in set(resident_context.activity_policy.allowed_actions):
        return _safe_result(outcome="POST_NOT_ALLOWED", tracker=tracker)
    try:
        joint_activity_runtime.complete_due_joint_activities(
            db,
            world_id=world_character.world_id,
            now=resident_context.run_started_at,
        )
    except joint_activity_runtime.JointActivityRuntimeError as exc:
        db.rollback()
        logger.exception(
            "joint_activity_completion_failed run_id=%s reason_code=%s",
            resident_context.run_id,
            exc.reason_code,
        )
        return _safe_result(
            outcome=exc.reason_code,
            tracker=tracker,
            status="failed",
            failure_class=type(exc).__name__,
        )

    try:
        activity_runtime.close_elapsed_dayparts(
            db,
            world_character_id=world_character.id,
            now=resident_context.run_started_at,
        )
    except activity_runtime.ActivityRuntimeError as exc:
        db.rollback()
        logger.exception(
            'routine_elapsed_daypart_transition_failed run_id=%s '
            'reason_code=%s',
            resident_context.run_id,
            str(exc),
        )
        return _safe_result(
            outcome=_runtime_error_code(exc),
            tracker=tracker,
            status='failed',
            failure_class=type(exc).__name__,
        )

    try:
        context = assemble_routine_post_context(
            db,
            world_character=world_character,
            character=resident_context.character,
            now=resident_context.run_started_at,
            interaction_source=interaction_source,
        )
    except RoutineContextUnavailable as exc:
        return _safe_result(outcome=exc.reason_code, tracker=tracker)
    joint_activity = (
        db.get(models.JointActivity, context.item.joint_activity_id)
        if context.item.joint_activity_id is not None
        else None
    )
    if context.item.joint_activity_id is not None and (
        joint_activity is None or joint_activity.world_id != context.world.id
    ):
        return _safe_result(outcome="JOINT_ACTIVITY_INVALID", tracker=tracker)
    if (
        joint_activity is not None
        and joint_activity.opening_post_id is None
        and joint_activity.status != "ready"
    ):
        return _safe_result(outcome="JOINT_ACTIVITY_NOT_READY", tracker=tracker)

    idempotency_key = _beat_idempotency_key(
        world_character_id=world_character.id,
        episode_id=context.episode.id,
        scheduled_for=context.due_tick.scheduled_for,
    )
    try:
        claim = activity_runtime.claim_activity_beat(
            db,
            episode_id=context.episode.id,
            scheduled_for=context.due_tick.scheduled_for,
            trigger_kind=(
                "comment_influenced" if context.source_events else "scheduled"
            ),
            idempotency_key=idempotency_key,
            claim_run_id=resident_context.run_id,
            claim_expires_at=resident_context.run_started_at + CLAIM_LEASE,
            source_event_ids=context.considered_source_event_ids,
            skipped_tick_count=context.due_tick.skipped_tick_count,
            now=resident_context.run_started_at,
        )
    except activity_runtime.ActivityRuntimeError as exc:
        return _safe_result(outcome=_runtime_error_code(exc), tracker=tracker)
    beat = claim.row
    if not isinstance(beat, models.ActivityBeat):
        raise TypeError("activity beat claim returned an invalid row")
    try:
        for event in context.source_events:
            activity_runtime.claim_event_consumption(
                db,
                world_id=context.world.id,
                consumer_world_character_id=world_character.id,
                source_social_event_id=event.source_event_id,
                target_activity_beat_id=beat.id,
                idempotency_key=f"{beat.id}:{event.source_event_id}",
                claim_run_id=resident_context.run_id,
                claim_expires_at=resident_context.run_started_at + CLAIM_LEASE,
                now=resident_context.run_started_at,
            )
    except activity_runtime.ActivityRuntimeError as exc:
        _finish_failed_beat(
            db,
            beat=beat,
            claim_run_id=resident_context.run_id,
            reason_code="source_event_claim_conflict",
            retryable=False,
        )
        return _safe_result(
            outcome=_runtime_error_code(exc),
            tracker=tracker,
            status="failed",
            failure_class=type(exc).__name__,
        )

    execution_signature = _execution_signature(
        world_character_id=world_character.id, beat_id=beat.id
    )
    existing_execution = agent_run_crud.get_public_action_execution_by_signature(
        db, execution_signature
    )
    if existing_execution is not None and existing_execution.status == "succeeded":
        result = existing_execution.result or {}
        return {
            "engine": "routine_resident_v1",
            "status": "completed",
            "summary": "Routine resident post evidence was reused.",
            "routine_outcome": "REUSED_SUCCESS",
            "publish_result": {
                "public_action_count": 1,
                "post_id": result.get("post_id"),
                "beat_id": beat.id,
                "reused": True,
            },
            "llm_usage_summary": tracker.summary(),
        }

    opening_claim: joint_activity_runtime.OpeningClaim | None = None
    if joint_activity is not None and joint_activity.opening_post_id is None:
        try:
            opening_claim = joint_activity_runtime.claim_opening(
                db,
                joint_activity_id=joint_activity.id,
                claimant_world_character_id=world_character.id,
                now=resident_context.run_started_at,
            )
        except joint_activity_runtime.JointActivityRuntimeError as exc:
            db.rollback()
            refreshed_joint = db.get(models.JointActivity, joint_activity.id)
            if (
                exc.reason_code == "joint_activity_already_opened"
                and refreshed_joint is not None
                and refreshed_joint.opening_post_id is not None
            ):
                joint_activity = refreshed_joint
            else:
                _finish_failed_beat(
                    db,
                    beat=beat,
                    claim_run_id=resident_context.run_id,
                    reason_code=exc.reason_code,
                    retryable=exc.reason_code == "joint_activity_opening_claimed",
                )
                return _safe_result(
                    outcome=exc.reason_code.upper(),
                    tracker=tracker,
                )

    try:
        generation = validate_routine_generation(
            await (provider or DirectRoutinePostProvider()).generate(
                resident_context=resident_context,
                routine_context=context,
                beat=beat,
                tracker=tracker,
            ),
            context=context,
            beat=beat,
        )
    except DirectLlmDeferred:
        if opening_claim is not None:
            joint_activity_runtime.release_opening(db, claim=opening_claim)
        _finish_failed_beat(
            db,
            beat=beat,
            claim_run_id=resident_context.run_id,
            reason_code="provider_deferred",
            retryable=True,
        )
        raise
    except Exception as exc:
        if opening_claim is not None:
            joint_activity_runtime.release_opening(db, claim=opening_claim)
        reason_code = _failure_code(exc)
        _finish_failed_beat(
            db,
            beat=beat,
            claim_run_id=resident_context.run_id,
            reason_code=reason_code,
            retryable=_retryable_provider_error(exc),
        )
        logger.warning(
            "routine_generation_failed run_id=%s beat_id=%s failure_class=%s",
            resident_context.run_id,
            beat.id,
            type(exc).__name__,
        )
        return _safe_result(
            outcome=reason_code,
            tracker=tracker,
            status="failed",
            failure_class=type(exc).__name__,
        )

    result_snapshot: dict[str, object] = {
        "routine_contract_version": ROUTINE_CONTRACT_VERSION,
        "planner_output_hash": _planner_hash(generation),
        "considered_source_event_ids": generation.plan.considered_source_event_ids,
        "used_source_event_ids": generation.plan.used_source_event_ids,
        "overflow_count": sum(context.overflow_reason_counts.values()),
        "overflow_reason_counts": context.overflow_reason_counts,
        "eligible_event_count": context.eligible_event_count,
        "serialized_event_count": len(context.source_events),
        "prompt_comment_chars": context.prompt_comment_chars,
        "provider_call_count": tracker.summary()["provider_call_count"],
        "scene_kind": generation.plan.scene_kind,
        "scene_brief": generation.plan.scene_brief,
        "continuity_facts": generation.plan.continuity_facts,
        "used_detail_keys": generation.plan.used_detail_keys,
    }

    try:
        with unit_of_work.deferred_commits():
            execution = agent_run_crud.create_public_action_execution(
                db,
                run_id=resident_context.run_id,
                character_id=resident_context.character.id,
                signature=execution_signature,
                scope="routine_activity_beat",
                action_type="post",
                brief_hash=result_snapshot["planner_output_hash"],
                world_id=context.world.id,
                actor_world_character_id=world_character.id,
            )
            post_read = community_service.create_agent_tool_post(
                db,
                resident_context.session_key,
                schemas.PostCreate(
                    title=generation.draft.title,
                    body=generation.draft.body,
                    author_character_id=resident_context.character.id,
                ),
                topic_signature=generation.draft.topic_signature,
                novelty_basis=generation.draft.novelty_basis,
                world_id=context.world.id,
                author_world_character_id=world_character.id,
            )
            post = db.get(models.Post, post_read.id)
            if post is None:
                raise activity_runtime.ActivityRuntimeValidationError(
                    "publish_evidence_missing"
                )
            result_snapshot["post_evidence"] = {
                "post_id": post.id,
                "world_id": post.world_id,
                "author_world_character_id": post.author_world_character_id,
            }
            post.joint_activity_id = context.item.joint_activity_id
            post.activity_episode_id = context.episode.id
            post.activity_beat_id = beat.id
            event_result = social_event_runtime.record_successful_social_event(
                db,
                world_id=context.world.id,
                actor_world_character_id=world_character.id,
                target_world_character_id=None,
                event_type="post_published",
                occurred_at=resident_context.run_started_at,
                idempotency_key=sha256(
                    f"p4|{execution.signature}|post_published".encode("utf-8")
                ).hexdigest(),
                evidence=social_event_runtime.EvidenceInput(
                    evidence_kind="post",
                    source_object_type="post",
                    source_object_id=post.id,
                    root_post_id=post.id,
                    source_post_id=post.id,
                    agent_run_id=resident_context.run_id,
                    public_action_execution_id=execution.id,
                    source_text=f"{post.title}\n{post.body}",
                    source_visibility_at_event=post.visibility,
                    source_author_id_at_event=world_character.id,
                ),
            )
            result_snapshot["social_event_id"] = event_result.event.id
            if joint_activity is not None:
                started_event = joint_activity_runtime.apply_joint_post(
                    db,
                    joint_activity_id=joint_activity.id,
                    author_world_character_id=world_character.id,
                    post=post,
                    post_event=event_result.event,
                    opening_claim=opening_claim,
                    now=resident_context.run_started_at,
                )
                result_snapshot["joint_activity_id"] = joint_activity.id
                result_snapshot["joint_opening_post_id"] = (
                    post.id if started_event is not None else joint_activity.opening_post_id
                )
                result_snapshot["joint_started_event_id"] = (
                    started_event.id if started_event is not None else None
                )
            activity_runtime.complete_activity_beat(
                db,
                beat_id=beat.id,
                claim_run_id=resident_context.run_id,
                source_post_id=post.id,
                state_after_snapshot=generation.state_after,
                result_snapshot=result_snapshot,
                now=resident_context.run_started_at,
                commit=False,
            )
            execution.target_post_id = post.id
            agent_run_crud.mark_public_action_execution_finished(
                db,
                execution,
                status="succeeded",
                result={
                    "post_id": post.id,
                    "beat_id": beat.id,
                    "world_id": context.world.id,
                    "world_character_id": world_character.id,
                    "social_event_id": event_result.event.id,
                    "joint_activity_id": (
                        joint_activity.id if joint_activity is not None else None
                    ),
                    "opening_post_id": post.opening_post_id,
                },
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        if opening_claim is not None:
            joint_activity_runtime.release_opening(db, claim=opening_claim)
        _finish_failed_beat(
            db,
            beat=beat,
            claim_run_id=resident_context.run_id,
            reason_code="publish_transaction_failed",
            retryable=isinstance(exc, IntegrityError),
        )
        logger.exception(
            "routine_publish_failed run_id=%s beat_id=%s failure_class=%s",
            resident_context.run_id,
            beat.id,
            type(exc).__name__,
        )
        return _safe_result(
            outcome="publish_transaction_failed",
            tracker=tracker,
            status="failed",
            failure_class=type(exc).__name__,
        )

    logger.info(
        "routine_post_succeeded run_id=%s world_id=%s world_character_id=%s "
        "episode_id=%s beat_id=%s sequence_no=%s source_event_count=%s "
        "used_event_count=%s provider_call_count=%s skipped_tick_count=%s",
        resident_context.run_id,
        context.world.id,
        world_character.id,
        context.episode.id,
        beat.id,
        beat.sequence_no,
        len(generation.plan.considered_source_event_ids),
        len(generation.plan.used_source_event_ids),
        tracker.summary()["provider_call_count"],
        context.due_tick.skipped_tick_count,
    )
    return {
        "engine": "routine_resident_v1",
        "status": "completed",
        "summary": "Routine resident continuous post completed.",
        "routine_outcome": "POST_SUCCEEDED",
        "publish_result": {
            "public_action_count": 1,
            "post_id": post.id,
            "beat_id": beat.id,
            "sequence_no": beat.sequence_no,
            "world_id": context.world.id,
            "world_character_id": world_character.id,
            "considered_event_count": len(
                generation.plan.considered_source_event_ids
            ),
            "used_event_count": len(generation.plan.used_source_event_ids),
        },
        "llm_usage_summary": tracker.summary(),
        "llm_rate_limit_waits": tracker.rate_limit_waits,
    }
