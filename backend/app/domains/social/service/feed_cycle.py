"""A World feed cycle: durable observation, bounded planning and atomic public effect.

Readiness, NO_ACTION, duplicate execution, stale target, retry and success paths
retain the original ordering and caller Session. Foreign owner/provider wiring
is supplied lazily; the service owns all transaction and result decisions.
"""

from __future__ import annotations
import logging
from time import perf_counter
from typing import Any
from pydantic import ValidationError
from app.core import unit_of_work
from app.domains.social.schemas import feed as schemas
from app.domains.social.contracts.feed_execution import (
    WorldFeedContext,
    WorldFeedWorkflows,
    FeedReactionProvider,
)
from app.domains.social.contracts.observations import SocialObservationError
from app.domains.social.contracts.search_state import SocialSearchUnavailable
from app.domains.social.exceptions import (
    WorldFeedReadinessError,
    FeedReactionValidationError,
)
from app.domains.social.service.feed_reaction_validation import (
    validate_reaction_decision,
)
from app.domains.social.service.feed_cycle_values import (
    _cycle_key,
    _execution_signature,
    _brief_hash,
    _declared_subjective_context,
    _safe_result,
    _summary,
)
from app.domains.social.service.feed_cycle_publishing import _publish_action
from app.domains.social.service.world_feed import (
    claim_cycle_keywords,
    claim_feed_observations,
    finalize_feed_cycle,
    mark_claims_retryable,
    load_ready_search_profile,
    search_world_feed_candidates,
    revalidate_candidate_actions,
)
from app.domains.social.repository.world_feed import get_feed_observation

logger = logging.getLogger("app.services.world_feed_runtime")


async def run_world_keyword_feed(
    ctx: WorldFeedContext,
    *,
    workflows: WorldFeedWorkflows,
    provider: FeedReactionProvider | None = None,
) -> dict[str, Any]:
    tracker = workflows.new_tracker(max_calls=3)
    active_world = workflows.active_world(ctx.db, ctx.character.id)
    if active_world is None:
        return _safe_result(
            outcome="world_character_not_ready",
            tracker=tracker,
        )
    try:
        profile = load_ready_search_profile(
            ctx.db,
            references=workflows.search_references(ctx.db),
            world_character_id=active_world.world_character_id,
        )
    except WorldFeedReadinessError as exc:
        return _safe_result(
            outcome=exc.reason_code,
            tracker=tracker,
            world_character_id=active_world.world_character_id,
        )
    if profile.imported_world_runtime_locked:
        return _safe_result(
            outcome="AUTONOMY_DISABLED",
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
        )

    cycle_key = _cycle_key(ctx, profile.world_character.id)
    try:
        claim = claim_cycle_keywords(
            ctx.db,
            profile=profile,
            cycle_key=cycle_key,
            run_id=ctx.run_id,
        )
        ctx.db.commit()
    except Exception as exc:
        ctx.db.rollback()
        logger.warning(
            "world_feed_claim_failed run_id=%s world_character_id=%s failure_class=%s",
            ctx.run_id,
            profile.world_character.id,
            type(exc).__name__,
        )
        return _safe_result(
            outcome="cursor_claim_failed",
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            status="failed",
            failure_class=type(exc).__name__,
        )
    if claim.duplicate_cycle:
        return _safe_result(
            outcome="duplicate_cycle",
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            summary=claim.previous_summary,
        )

    try:
        search = search_world_feed_candidates(
            ctx.db,
            references=workflows.search_references(ctx.db),
            profile=profile,
            keywords=claim.keywords,
            allowed_policy_actions=ctx.activity_policy.allowed_actions,
            now=ctx.run_started_at,
            search_index=ctx.social_search_index,
            search_state=ctx.social_search_state,
        )
    except SocialSearchUnavailable as exc:
        reason: schemas.FeedNoActionReason = exc.state.value
        cycle_summary = _summary(
            ctx=ctx,
            profile=profile,
            claim=claim,
            raw_candidate_count=0,
            filtered_candidate_count=0,
            claimed_candidate_count=0,
            selected_action=None,
            interaction_intent=None,
            outcome="DEGRADED",
            reason_code=reason,
            query_latency_ms=0,
            planner_latency_ms=0,
            writer_latency_ms=None,
            tracker=tracker,
        )
        finalize_feed_cycle(
            ctx.db,
            profile=profile,
            claim=claim,
            observations=(),
            selected_index=None,
            selected_action=None,
            interaction_intent=None,
            comment_purpose=None,
            reason_code=reason,
            public_action_execution_id=None,
            summary=cycle_summary,
            now=ctx.run_started_at,
        )
        ctx.db.commit()
        return _safe_result(
            outcome=reason,
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            status="degraded",
            summary=cycle_summary,
        )
    claims = claim_feed_observations(
        ctx.db,
        profile=profile,
        candidates=search.candidates,
        cycle_key=cycle_key,
        run_id=ctx.run_id,
        now=ctx.run_started_at,
    )
    ctx.db.commit()
    if not claims.candidates:
        reason: schemas.FeedNoActionReason = (
            "no_candidate" if search.raw_candidate_count == 0 else "no_allowed_action"
        )
        cycle_summary = _summary(
            ctx=ctx,
            profile=profile,
            claim=claim,
            raw_candidate_count=search.raw_candidate_count,
            filtered_candidate_count=search.filtered_candidate_count,
            claimed_candidate_count=0,
            selected_action=None,
            interaction_intent=None,
            outcome="NO_ACTION",
            reason_code=reason,
            query_latency_ms=search.query_latency_ms,
            planner_latency_ms=0,
            writer_latency_ms=None,
            tracker=tracker,
            claim_conflict_count=claims.claim_conflict_count,
        )
        finalize_feed_cycle(
            ctx.db,
            profile=profile,
            claim=claim,
            observations=(),
            selected_index=None,
            selected_action=None,
            interaction_intent=None,
            comment_purpose=None,
            reason_code=reason,
            public_action_execution_id=None,
            summary=cycle_summary,
            now=ctx.run_started_at,
        )
        ctx.db.commit()
        return _safe_result(
            outcome=reason,
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            summary=cycle_summary,
        )

    observation_receipts = []
    try:
        for candidate in claims.candidates:
            observation_receipts.append(
                workflows.observe_source(
                    ctx.db,
                    world_id=profile.world.id,
                    observer_world_character_id=profile.world_character.id,
                    source_social_event_id=None,
                    source_post_id=candidate.post_id,
                    lane="feed",
                    observed_at=ctx.run_started_at,
                )
            )
        # Observation is durable before planning. A later NO_ACTION or failed
        # follow-up must never erase the fact that the source entered context.
        ctx.db.commit()
    except SocialObservationError as exc:
        ctx.db.rollback()
        mark_claims_retryable(
            ctx.db, observations=claims.observations, now=ctx.run_started_at
        )
        ctx.db.commit()
        logger.warning(
            "world_feed_observation_failed run_id=%s world_id=%s reason_code=%s",
            ctx.run_id,
            profile.world.id,
            exc.reason_code,
        )
        return _safe_result(
            outcome="observation_failed",
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            status="failed",
            failure_class=exc.reason_code,
            summary={
                "outcome": "OBSERVATION_FAILED",
                "reason_code": exc.reason_code,
                "observation_receipt_count": 0,
            },
        )

    proposal_eligible_indices = frozenset(
        candidate.candidate_index
        for candidate in claims.candidates
        if workflows.proposals.proposal_eligibility(
            ctx.db,
            actor_world_character_id=profile.world_character.id,
            target_post_id=candidate.post_id,
            now=ctx.run_started_at,
        ).eligible
    )
    reaction_provider = provider or workflows.default_provider()
    planner_started = perf_counter()
    try:
        decision = validate_reaction_decision(
            await reaction_provider.plan(
                resident_context=ctx,
                profile=profile,
                candidates=claims.candidates,
                tracker=tracker,
                proposal_eligible_indices=proposal_eligible_indices,
            ),
            candidates=claims.candidates,
            proposal_eligible_indices=proposal_eligible_indices,
        )
    except workflows.llm_deferred:
        mark_claims_retryable(
            ctx.db, observations=claims.observations, now=ctx.run_started_at
        )
        ctx.db.commit()
        raise
    except (
        workflows.llm_error,
        ValidationError,
        FeedReactionValidationError,
        ValueError,
    ) as exc:
        mark_claims_retryable(
            ctx.db, observations=claims.observations, now=ctx.run_started_at
        )
        ctx.db.commit()
        logger.warning(
            "world_feed_planner_failed run_id=%s world_id=%s failure_class=%s",
            ctx.run_id,
            profile.world.id,
            type(exc).__name__,
        )
        return _safe_result(
            outcome="planner_failed",
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            status="failed",
            failure_class=type(exc).__name__,
            summary={
                "outcome": "FOLLOW_UP_PLANNING_FAILED",
                "reason_code": "planner_failed",
                "observation_receipt_count": len(observation_receipts),
            },
        )
    planner_latency_ms = int((perf_counter() - planner_started) * 1000)

    if decision.selected_action is None:
        reason = decision.reason_code or "model_abstained"
        cycle_summary = _summary(
            ctx=ctx,
            profile=profile,
            claim=claim,
            raw_candidate_count=search.raw_candidate_count,
            filtered_candidate_count=search.filtered_candidate_count,
            claimed_candidate_count=len(claims.observations),
            selected_action=None,
            interaction_intent=None,
            outcome="NO_ACTION",
            reason_code=reason,
            query_latency_ms=search.query_latency_ms,
            planner_latency_ms=planner_latency_ms,
            writer_latency_ms=None,
            tracker=tracker,
            claim_conflict_count=claims.claim_conflict_count,
            observation_receipt_count=len(observation_receipts),
        )
        finalize_feed_cycle(
            ctx.db,
            profile=profile,
            claim=claim,
            observations=claims.observations,
            selected_index=None,
            selected_action=None,
            interaction_intent=None,
            comment_purpose=None,
            reason_code=reason,
            public_action_execution_id=None,
            summary=cycle_summary,
            now=ctx.run_started_at,
        )
        ctx.db.commit()
        return _safe_result(
            outcome=reason,
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            summary=cycle_summary,
        )

    selected_index = int(decision.selected_candidate_index or 0)
    candidate = claims.candidates[selected_index]
    draft: schemas.FeedCommentDraft | schemas.JointActivityProposalPreview | None = None
    writer_latency_ms: int | None = None
    if decision.selected_action == "comment":
        writer_started = perf_counter()
        try:
            writer_result = await reaction_provider.write_comment(
                resident_context=ctx,
                profile=profile,
                candidate=candidate,
                decision=decision,
                tracker=tracker,
            )
            if decision.interaction_intent == "ordinary_comment":
                if not isinstance(writer_result, schemas.FeedCommentDraft):
                    raise FeedReactionValidationError(
                        "ordinary writer returned proposal"
                    )
            elif not isinstance(writer_result, schemas.JointActivityProposalPreview):
                raise FeedReactionValidationError("proposal writer returned comment")
            draft = writer_result
            if isinstance(draft, schemas.JointActivityProposalPreview):
                workflows.proposals.validate_preview(
                    ctx.db,
                    preview=draft,
                    world_id=profile.world.id,
                    proposer_world_character_id=profile.world_character.id,
                    target_post_id=candidate.post_id,
                    now=ctx.run_started_at,
                )
        except workflows.llm_deferred:
            mark_claims_retryable(
                ctx.db, observations=claims.observations, now=ctx.run_started_at
            )
            ctx.db.commit()
            raise
        except workflows.llm_json_error:
            reason = "writer_invalid"
            writer_latency_ms = int((perf_counter() - writer_started) * 1000)
            cycle_summary = _summary(
                ctx=ctx,
                profile=profile,
                claim=claim,
                raw_candidate_count=search.raw_candidate_count,
                filtered_candidate_count=search.filtered_candidate_count,
                claimed_candidate_count=len(claims.observations),
                selected_action=None,
                interaction_intent=decision.interaction_intent,
                outcome="NO_ACTION",
                reason_code=reason,
                query_latency_ms=search.query_latency_ms,
                planner_latency_ms=planner_latency_ms,
                writer_latency_ms=writer_latency_ms,
                tracker=tracker,
                claim_conflict_count=claims.claim_conflict_count,
                observation_receipt_count=len(observation_receipts),
            )
            finalize_feed_cycle(
                ctx.db,
                profile=profile,
                claim=claim,
                observations=claims.observations,
                selected_index=None,
                selected_action=None,
                interaction_intent=None,
                comment_purpose=None,
                reason_code=reason,
                public_action_execution_id=None,
                summary=cycle_summary,
                now=ctx.run_started_at,
            )
            ctx.db.commit()
            return _safe_result(
                outcome=reason,
                tracker=tracker,
                world_id=profile.world.id,
                world_character_id=profile.world_character.id,
                summary=cycle_summary,
            )
        except (workflows.llm_error, ValidationError, ValueError) as exc:
            mark_claims_retryable(
                ctx.db, observations=claims.observations, now=ctx.run_started_at
            )
            ctx.db.commit()
            return _safe_result(
                outcome="writer_failed",
                tracker=tracker,
                world_id=profile.world.id,
                world_character_id=profile.world_character.id,
                status="failed",
                failure_class=type(exc).__name__,
                summary={
                    "outcome": "FOLLOW_UP_FAILED",
                    "reason_code": "writer_failed",
                    "observation_receipt_count": len(observation_receipts),
                },
            )
        writer_latency_ms = int((perf_counter() - writer_started) * 1000)

    fresh = revalidate_candidate_actions(
        ctx.db,
        references=workflows.search_references(ctx.db),
        profile=profile,
        candidate=candidate,
        allowed_policy_actions=ctx.activity_policy.allowed_actions,
    )
    if fresh is None or decision.selected_action not in fresh[1]:
        reason = "target_stale"
        cycle_summary = _summary(
            ctx=ctx,
            profile=profile,
            claim=claim,
            raw_candidate_count=search.raw_candidate_count,
            filtered_candidate_count=search.filtered_candidate_count,
            claimed_candidate_count=len(claims.observations),
            selected_action=None,
            interaction_intent=decision.interaction_intent,
            outcome="NO_ACTION",
            reason_code=reason,
            query_latency_ms=search.query_latency_ms,
            planner_latency_ms=planner_latency_ms,
            writer_latency_ms=writer_latency_ms,
            tracker=tracker,
            claim_conflict_count=claims.claim_conflict_count,
            observation_receipt_count=len(observation_receipts),
        )
        finalize_feed_cycle(
            ctx.db,
            profile=profile,
            claim=claim,
            observations=claims.observations,
            selected_index=None,
            selected_action=None,
            interaction_intent=None,
            comment_purpose=None,
            reason_code=reason,
            public_action_execution_id=None,
            summary=cycle_summary,
            now=ctx.run_started_at,
        )
        ctx.db.commit()
        return _safe_result(
            outcome=reason,
            tracker=tracker,
            world_id=profile.world.id,
            world_character_id=profile.world_character.id,
            summary=cycle_summary,
        )

    observation = claims.observations[selected_index]
    signature = _execution_signature(
        profile=profile,
        candidate=candidate,
        decision=decision,
        cycle_key=cycle_key,
    )
    existing_execution = workflows.executions.get_public_action_execution_by_signature(
        ctx.db, signature
    )
    if existing_execution is not None and existing_execution.status == "succeeded":
        action_result = dict(existing_execution.result or {})
        execution = existing_execution
        cycle_summary = _summary(
            ctx=ctx,
            profile=profile,
            claim=claim,
            raw_candidate_count=search.raw_candidate_count,
            filtered_candidate_count=search.filtered_candidate_count,
            claimed_candidate_count=len(claims.observations),
            selected_action=decision.selected_action,
            interaction_intent=decision.interaction_intent,
            outcome="ACTION_REUSED",
            reason_code=None,
            query_latency_ms=search.query_latency_ms,
            planner_latency_ms=planner_latency_ms,
            writer_latency_ms=writer_latency_ms,
            tracker=tracker,
            public_action_execution_id=execution.id,
            claim_conflict_count=claims.claim_conflict_count,
            observation_receipt_count=len(observation_receipts),
        )
        finalize_feed_cycle(
            ctx.db,
            profile=profile,
            claim=claim,
            observations=claims.observations,
            selected_index=selected_index,
            selected_action=decision.selected_action,
            interaction_intent=decision.interaction_intent,
            comment_purpose=decision.comment_purpose,
            reason_code=None,
            public_action_execution_id=execution.id,
            summary=cycle_summary,
            now=ctx.run_started_at,
        )
        ctx.db.commit()
    else:
        try:
            with unit_of_work.deferred_commits():
                execution = workflows.executions.create_public_action_execution(
                    ctx.db,
                    run_id=ctx.run_id,
                    character_id=ctx.character.id,
                    signature=signature,
                    scope="world_keyword_feed",
                    action_type=decision.selected_action,
                    target_post_id=candidate.post_id,
                    target_profile_type=(
                        "character" if decision.selected_action == "follow" else None
                    ),
                    target_profile_id=(
                        candidate.author_character_id
                        if decision.selected_action == "follow"
                        else None
                    ),
                    brief_hash=_brief_hash(decision.brief),
                    world_id=profile.world.id,
                    actor_world_character_id=profile.world_character.id,
                    feed_observation_id=observation.id,
                    interaction_intent=decision.interaction_intent,
                    comment_purpose=decision.comment_purpose,
                )
                action_result = _publish_action(
                    ctx,
                    workflows=workflows.publishing,
                    candidate=candidate,
                    decision=decision,
                    draft=draft,
                )
                social_apply = (
                    workflows.social_apply.apply_successful_world_feed_action(
                        ctx.db,
                        profile=profile,
                        candidate=candidate,
                        decision=decision,
                        draft=draft,
                        action_result=action_result,
                        execution=execution,
                        occurred_at=ctx.run_started_at,
                    )
                )
                action_result.update(
                    {
                        "world_id": profile.world.id,
                        "actor_world_character_id": profile.world_character.id,
                        "target_world_character_id": candidate.author_world_character_id,
                        "feed_observation_id": observation.id,
                        "interaction_intent": decision.interaction_intent,
                        "comment_purpose": decision.comment_purpose,
                        "social_event_id": social_apply.event.id,
                        "proposal_id": (
                            social_apply.proposal.id
                            if social_apply.proposal is not None
                            else None
                        ),
                    }
                )
                workflows.executions.mark_public_action_execution_finished(
                    ctx.db,
                    execution,
                    status="succeeded",
                    result=action_result,
                )
                workflows.record_declared_subjective_context(
                    ctx.db,
                    execution=execution,
                    event=social_apply.event,
                    source_post_id=str(
                        action_result.get("post_id") or candidate.post_id
                    ),
                    context=_declared_subjective_context(decision),
                    captured_at=ctx.run_started_at,
                )
                cycle_summary = _summary(
                    ctx=ctx,
                    profile=profile,
                    claim=claim,
                    raw_candidate_count=search.raw_candidate_count,
                    filtered_candidate_count=search.filtered_candidate_count,
                    claimed_candidate_count=len(claims.observations),
                    selected_action=decision.selected_action,
                    interaction_intent=decision.interaction_intent,
                    outcome="ACTION_SUCCEEDED",
                    reason_code=None,
                    query_latency_ms=search.query_latency_ms,
                    planner_latency_ms=planner_latency_ms,
                    writer_latency_ms=writer_latency_ms,
                    tracker=tracker,
                    public_action_execution_id=execution.id,
                    claim_conflict_count=claims.claim_conflict_count,
                    observation_receipt_count=len(observation_receipts),
                )
                finalize_feed_cycle(
                    ctx.db,
                    profile=profile,
                    claim=claim,
                    observations=claims.observations,
                    selected_index=selected_index,
                    selected_action=decision.selected_action,
                    interaction_intent=decision.interaction_intent,
                    comment_purpose=decision.comment_purpose,
                    reason_code=None,
                    public_action_execution_id=execution.id,
                    summary=cycle_summary,
                    now=ctx.run_started_at,
                )
            ctx.db.commit()
        except Exception as exc:
            ctx.db.rollback()
            refreshed = tuple(
                row
                for observation in claims.observations
                if (row := get_feed_observation(ctx.db, observation.id)) is not None
            )
            mark_claims_retryable(
                ctx.db,
                observations=refreshed,
                now=ctx.run_started_at,
            )
            ctx.db.commit()
            logger.warning(
                "world_feed_publish_failed run_id=%s world_id=%s action=%s failure_class=%s",
                ctx.run_id,
                profile.world.id,
                decision.selected_action,
                type(exc).__name__,
            )
            return _safe_result(
                outcome="public_action_failed",
                tracker=tracker,
                world_id=profile.world.id,
                world_character_id=profile.world_character.id,
                status="failed",
                failure_class=type(exc).__name__,
            )

    logger.info(
        "world_feed_cycle_completed run_id=%s world_id=%s world_character_id=%s "
        "raw_candidates=%s filtered_candidates=%s claimed_candidates=%s "
        "selected_action=%s interaction_intent=%s provider_requests=%s",
        ctx.run_id,
        profile.world.id,
        profile.world_character.id,
        search.raw_candidate_count,
        search.filtered_candidate_count,
        len(claims.observations),
        decision.selected_action,
        decision.interaction_intent,
        tracker.summary()["provider_call_count"],
    )
    return {
        "engine": "keyword_search_v1",
        "status": "completed",
        "summary": "World keyword feed public reaction completed.",
        "feed_outcome": "ACTION_SUCCEEDED",
        "world_id": profile.world.id,
        "world_character_id": profile.world_character.id,
        "feed_cycle_summary": cycle_summary,
        "publish_result": {
            "public_action_count": 1,
            "action": decision.selected_action,
            "target_post_id": candidate.post_id,
            "result": action_result,
        },
        "llm_usage_summary": tracker.summary(),
    }
