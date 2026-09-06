"""World feed cycle identity, declaration and durable outcome presentation."""

from datetime import UTC, datetime
from hashlib import sha256
from app.domains.social.schemas import feed as schemas
from app.domains.social.contracts.feed_execution import (
    WorldFeedContext,
    ReactionTracker,
)
from app.domains.social.contracts.world_feed import ReadySearchProfile, KeywordClaim
from app.domains.social.contracts.subjective_context import (
    ActionEmotionLabel,
    ActionSubjectiveContextV1,
)
from app.domains.social.constants import WORLD_FEED_RUNTIME_VERSION


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cycle_key(ctx: WorldFeedContext, world_character_id: str) -> str:
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


def _declared_subjective_context(
    decision: schemas.FeedReactionDecision,
) -> ActionSubjectiveContextV1 | None:
    action = decision.selected_action
    if (
        action is None
        or decision.motivation_kind is None
        or decision.motivation_text is None
    ):
        return None
    return ActionSubjectiveContextV1(
        motivation_kind=decision.motivation_kind,
        motivation_text=decision.motivation_text,
        emotion_label=decision.emotion_label or ActionEmotionLabel.UNSPECIFIED,
        emotion_text=decision.emotion_text,
        emotion_intensity=decision.emotion_intensity,
    )


def _safe_result(
    *,
    outcome: str,
    tracker: ReactionTracker,
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
    ctx: WorldFeedContext,
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
    tracker: ReactionTracker,
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
