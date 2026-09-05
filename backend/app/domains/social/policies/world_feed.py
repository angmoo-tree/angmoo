"""World feed action eligibility, age and timezone presentation."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.domains.social.contracts.world_feed import ReadySearchProfile, FeedPost
from app.domains.social.schemas import feed as feed_schemas


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _action_weight(action_profile: dict[str, object], action: str) -> int:
    raw = action_profile.get(action)
    if not isinstance(raw, dict):
        return 0
    try:
        return max(0, min(100, int(raw.get("weight") or 0)))
    except (TypeError, ValueError):
        return 0


def _age_bucket(age_seconds: int) -> str:
    if age_seconds < 24 * 60 * 60:
        return "recent"
    if age_seconds < 7 * 24 * 60 * 60:
        return "days_old"
    if age_seconds < 28 * 24 * 60 * 60:
        return "weeks_old"
    return "older"


def _local_datetime(value: datetime, timezone_name: str) -> str:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = UTC
    return _aware_utc(value).astimezone(zone).isoformat()


def _allowed_actions(
    *,
    actor: ReadySearchProfile,
    post: FeedPost,
    policy_actions: set[str],
    liked: set[str],
    commented: set[str],
    reposted: set[str],
    followed: set[str],
) -> list[feed_schemas.FeedAction]:
    allowed: list[feed_schemas.FeedAction] = []
    if (
        "like" in policy_actions
        and _action_weight(actor.action_profile, "like") > 0
        and post.id not in liked
    ):
        allowed.append("like")
    if (
        ("comment" in policy_actions or "reply" in policy_actions)
        and _action_weight(actor.action_profile, "comment") > 0
        and post.id not in commented
    ):
        allowed.append("comment")
    if (
        "repost" in policy_actions
        and _action_weight(actor.action_profile, "repost") > 0
        and post.id not in reposted
    ):
        allowed.append("repost")
    if (
        "follow" in policy_actions
        and _action_weight(actor.action_profile, "follow") > 0
        and post.author_character_id not in followed
    ):
        allowed.append("follow")
    return allowed
