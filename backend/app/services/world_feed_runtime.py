from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import logging
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from app import models, schemas
from app.runtime.social.observations import observe_source
from app.core import unit_of_work
from app.cruds import agent_runs as agent_run_crud
from app.domains.social.public import SocialObservationError, SocialSearchUnavailable
from app.services import (
    activity_proposal_runtime,
    community as community_service,
    world_feed_social_apply,
)
from app.services.direct_llm import (
    DirectLlmDeferred,
    DirectLlmError,
    DirectLlmJsonError,
    RunLlmTracker,
)
from app.services.feed_reaction_planner import (
    DirectFeedReactionProvider,
    FeedReactionProvider,
    FeedReactionValidationError,
    validate_reaction_decision,
)
from app.services.resident_contracts import LangGraphResidentContext
from app.services.world_feed_search import (
    KeywordClaim,
    ReadySearchProfile,
    WorldFeedReadinessError,
    claim_cycle_keywords,
    claim_feed_observations,
    finalize_feed_cycle,
    load_ready_search_profile,
    mark_claims_retryable,
    revalidate_candidate_actions,
    search_world_feed_candidates,
)


logger = logging.getLogger(__name__)
WORLD_FEED_RUNTIME_VERSION = "world-keyword-feed-runtime-v1"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cycle_key(ctx: LangGraphResidentContext, world_character_id: str) -> str:
    minute = _aware_utc(ctx.run_started_at).replace(second=0, microsecond=0)
    raw = "|".join(
        (
            WORLD_FEED_RUNTIME_VERSION,
            world_character_id,
            minute.isoformat(),
            ctx.run_mode,
        )
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _execution_signature(
    *,
    profile: ReadySearchProfile,
    candidate: schemas.WorldFeedCandidateRead,
    decision: schemas.FeedReactionDecision,
    cycle_key: str,
) -> str:
    raw = "|".join(
        (
            WORLD_FEED_RUNTIME_VERSION,
            profile.world_character.id,
            profile.world.id,
            str(decision.selected_action or ""),
            candidate.post_id,
            str(decision.interaction_intent or ""),
            cycle_key,
        )
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _brief_hash(brief: str | None) -> str | None:
    if not brief:
        return None
    return sha256(brief.encode("utf-8")).hexdigest()


def _safe_result(
    *,
    outcome: str,
    tracker: RunLlmTracker,
    world_id: str | None = None,
    world_character_id: str | None = None,
    status: str = "observed",
    summary: dict[str, object] | None = None,
    failure_class: str | None = None,
) -> dict[str, object]:
    return {
        "engine": "keyword_search_v1",
        "status": status,
        "summary": f"World keyword feed outcome: {outcome}.",
        "feed_outcome": outcome,
        "world_id": world_id,
        "world_character_id": world_character_id,
        "failure_class": failure_class,
        "feed_cycle_summary": summary or {},
        "publish_result": {"public_action_count": 0},
        "llm_usage_summary": tracker.summary(),
    }


def _summary(
    *,
    ctx: LangGraphResidentContext,
    profile: ReadySearchProfile,
    claim: KeywordClaim,
    raw_candidate_count: int,
    filtered_candidate_count: int,
    claimed_candidate_count: int,
    selected_action: str | None,
    interaction_intent: str | None,
    outcome: str,
    reason_code: str | None,
    query_latency_ms: int,
    planner_latency_ms: int,
    writer_latency_ms: int | None,
    tracker: RunLlmTracker,
    public_action_execution_id: int | None = None,
    claim_conflict_count: int = 0,
    observation_receipt_count: int = 0,
) -> dict[str, object]:
    return {
        "runtime_version": WORLD_FEED_RUNTIME_VERSION,
        "run_id": ctx.run_id,
        "world_id": profile.world.id,
        "world_character_id": profile.world_character.id,
        "feed_runtime_mode": profile.world_character.feed_runtime_mode,
        "keyword_count": len(claim.keywords),
        "keywords": list(claim.keywords),
        "keyword_offset": claim.cursor_offset,
        "raw_candidate_count": raw_candidate_count,
        "filtered_candidate_count": filtered_candidate_count,
        "claimed_candidate_count": claimed_candidate_count,
        "claim_conflict_count": claim_conflict_count,
        "observation_receipt_count": observation_receipt_count,
        "selected_action": selected_action,
        "interaction_intent": interaction_intent,
        "outcome": outcome,
        "reason_code": reason_code,
        "query_latency_ms": query_latency_ms,
        "planner_latency_ms": planner_latency_ms,
        "writer_latency_ms": writer_latency_ms,
        "physical_request_count": tracker.summary()["provider_call_count"],
        "public_action_execution_id": public_action_execution_id,
    }


def _publish_action(
    ctx: LangGraphResidentContext,
    *,
    candidate: schemas.WorldFeedCandidateRead,
    decision: schemas.FeedReactionDecision,
    draft: schemas.FeedCommentDraft | schemas.JointActivityProposalPreview | None,
) -> dict[str, object]:
    action = decision.selected_action
    if action == "like":
        post = community_service.like_agent_tool_post(
            ctx.db,
            ctx.session_key,
            candidate.post_id,
            schemas.PostLikeCreate(character_id=ctx.character.id),
        )
        return {"post_id": post.id, "action": "like"}
    if action == "comment":
        if draft is None:
            raise FeedReactionValidationError("ordinary comment draft is missing")
        reply = community_service.reply_agent_tool_post(
            ctx.db,
            ctx.session_key,
            candidate.post_id,
            schemas.TimelineReplyCreate(
                body=draft.text,
                author_character_id=ctx.character.id,
            ),
        )
        return {
            "post_id": reply.id,
            "reply_to_post_id": candidate.post_id,
            "action": "comment",
        }
    if action == "repost":
        repost = community_service.repost_agent_tool_post(
            ctx.db,
            ctx.session_key,
            candidate.post_id,
            schemas.PostLikeCreate(character_id=ctx.character.id),
        )
        return {
            "post_id": repost.id,
            "repost_of_post_id": candidate.post_id,
            "action": "repost",
        }
    if action == "follow":
        follow = community_service.follow_agent_tool_profile(
            ctx.db,
            ctx.session_key,
            schemas.FollowCreate(
                target_type="character",
                target_id=candidate.author_character_id,
                follower_character_id=ctx.character.id,
            ),
        )
        return {
            "target_character_id": follow.target.id,
            "source_post_id": candidate.post_id,
            "action": "follow",
        }
    raise FeedReactionValidationError("unsupported feed action")


async def run_world_keyword_feed(
    ctx: LangGraphResidentContext,
    *,
    provider: FeedReactionProvider | None = None,
) -> dict[str, Any]:
    tracker = RunLlmTracker(max_calls=3)
    active_world = ctx.db.get(models.CharacterActiveWorld, ctx.character.id)
    if active_world is None:
        return _safe_result(
            outcome="world_character_not_ready",
            tracker=tracker,
        )
    try:
        profile = load_ready_search_profile(
            ctx.db,
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
            "no_candidate"
            if search.raw_candidate_count == 0
            else "no_allowed_action"
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
                observe_source(
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
        if activity_proposal_runtime.proposal_eligibility(
            ctx.db,
            actor_world_character_id=profile.world_character.id,
            target_post_id=candidate.post_id,
            now=ctx.run_started_at,
        ).eligible
    )
    reaction_provider = provider or DirectFeedReactionProvider()
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
    except DirectLlmDeferred:
        mark_claims_retryable(
            ctx.db, observations=claims.observations, now=ctx.run_started_at
        )
        ctx.db.commit()
        raise
    except (DirectLlmError, ValidationError, FeedReactionValidationError, ValueError) as exc:
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
                    raise FeedReactionValidationError("ordinary writer returned proposal")
            elif not isinstance(writer_result, schemas.JointActivityProposalPreview):
                raise FeedReactionValidationError("proposal writer returned comment")
            draft = writer_result
            if isinstance(draft, schemas.JointActivityProposalPreview):
                activity_proposal_runtime.validate_preview(
                    ctx.db,
                    preview=draft,
                    world_id=profile.world.id,
                    proposer_world_character_id=profile.world_character.id,
                    target_post_id=candidate.post_id,
                    now=ctx.run_started_at,
                )
        except DirectLlmDeferred:
            mark_claims_retryable(
                ctx.db, observations=claims.observations, now=ctx.run_started_at
            )
            ctx.db.commit()
            raise
        except DirectLlmJsonError:
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
        except (DirectLlmError, ValidationError, ValueError) as exc:
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
    existing_execution = agent_run_crud.get_public_action_execution_by_signature(
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
                execution = agent_run_crud.create_public_action_execution(
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
                    candidate=candidate,
                    decision=decision,
                    draft=draft,
                )
                social_apply = (
                    world_feed_social_apply.apply_successful_world_feed_action(
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
                agent_run_crud.mark_public_action_execution_finished(
                    ctx.db,
                    execution,
                    status="succeeded",
                    result=action_result,
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
                if (
                    row := ctx.db.get(
                        models.WorldCharacterFeedObservation, observation.id
                    )
                )
                is not None
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
