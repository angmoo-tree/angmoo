from typing import Any

from app.services.llm_context import neutralize_context_text


PREPARED_CREATE_POST_BRIEF_SENTINEL = "__ANGMOO_USE_PREPARED_FEED_SCAN_BRIEF__"
POST_SEED_INTENTS = {"own_thought", "public_reaction"}
WRITABLE_POST_SEED_INTENTS = {"own_thought"}
LEGACY_POST_SEED_INTENTS = {"direct_address": "public_reaction"}


def is_feed_scan_community_theme_brief(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.replace("\r\n", "\n").strip().lower()
    return (
        "source: feed_scan" in normalized
        and "writing_mode: community_theme_post" in normalized
    )


def normalize_post_seed_intent(value: Any, *, post_seed: Any = None) -> str:
    if post_seed is not None and not str(post_seed or "").strip():
        return ""
    intent = _brief_field(value, 40)
    intent = LEGACY_POST_SEED_INTENTS.get(intent, intent)
    return intent if intent in POST_SEED_INTENTS else ""


def build_feed_scan_create_post_brief(
    feed_interest_payload: dict[str, Any],
    *,
    feed_cue_topic: Any = None,
) -> str:
    feed_cue = _brief_field(feed_cue_topic, 300)
    if feed_cue:
        return "\n".join(
            [
                "source: owner_feed_cue",
                "writing_mode: owner_feed_cue_post",
                f"primary_intent: {feed_cue}",
                "instruction: 사용자가 준 모이 주제를 캐릭터 페르소나와 말투에 맞춰 새 원문 지저귐으로 풀어쓴다.",
            ]
        )

    interests = feed_interest_payload.get("interests")
    first_interest: dict[str, Any] = {}
    if isinstance(interests, list):
        for item in interests:
            if isinstance(item, dict):
                first_interest = item
                break
    if not first_interest or bool(feed_interest_payload.get("no_relevant_signal")):
        return ""

    post_seed = _brief_field(feed_interest_payload.get("post_seed"), 240)
    post_seed_intent = normalize_post_seed_intent(
        feed_interest_payload.get("post_seed_intent"), post_seed=post_seed
    )
    summary = _brief_field(first_interest.get("summary"), 220)
    reason = _brief_field(first_interest.get("reason"), 280)
    review_reason = _brief_field(feed_interest_payload.get("review_reason"), 280)
    topic_signature = _brief_field(feed_interest_payload.get("topic_signature"), 300)
    novelty_basis = _brief_field(feed_interest_payload.get("novelty_basis"), 500)
    if not post_seed:
        return ""
    if post_seed_intent not in WRITABLE_POST_SEED_INTENTS:
        return ""

    return "\n".join(
        [
            "source: feed_scan",
            "writing_mode: community_theme_post",
            f"primary_intent: {post_seed}",
            f"primary_intent_type: {post_seed_intent or '-'}",
            "supporting_context:",
            f"topic_signature: {topic_signature or '-'}",
            f"novelty_basis: {novelty_basis or '-'}",
            f"summary: {summary or '-'}",
            f"reason: {reason or '-'}",
            f"review_reason: {review_reason or '-'}",
        ]
    )


def build_self_update_create_post_brief() -> str:
    return "\n".join(
        [
            "source: self_update",
            "writing_mode: self_update_post",
            "basis: current_time_and_persona",
            "instruction: 현재 시간, 캐릭터 페르소나, 말투, 세계관, 관심사를 바탕으로 작은 근황/생각/질문/취미 기록을 쓴다.",
        ]
    )


def _brief_field(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = " ".join(neutralize_context_text(str(value)).split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."
