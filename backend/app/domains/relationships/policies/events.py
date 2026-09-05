"""Deterministic event deltas and snapshots without database or provider access."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.domains.relationships.contracts.events import _Delta, EventWorld, RelationshipStateValues, EventPost
from app.domains.relationships.exceptions import SocialEventRuntimeError


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _world_zone(world: EventWorld) -> ZoneInfo:
    try:
        return ZoneInfo(world.timezone)
    except ZoneInfoNotFoundError as exc:
        raise SocialEventRuntimeError("world_timezone_invalid") from exc


def _local_day_bounds(world: EventWorld, occurred_at: datetime) -> tuple[datetime, datetime]:
    zone = _world_zone(world)
    local_date = _aware_utc(occurred_at).astimezone(zone).date()
    start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(UTC)
    return start, start + timedelta(days=1)


def _snapshot(state: RelationshipStateValues) -> dict[str, int]:
    return {
        "familiarity": state.familiarity,
        "affinity": state.affinity,
        "trust": state.trust,
        "tension": state.tension,
        "interaction_count": state.interaction_count,
        "version": state.version,
    }


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _purpose_delta(event_type: str, purpose: str | None) -> _Delta:
    positive = {"empathy", "encouragement", "humor"}
    neutral = {"question", "advice", "information", "observation"}
    if purpose in positive:
        valence, intensity = "positive", "low"
        affinity = 1 if event_type == "comment_created" else 2
        trust = 0 if event_type == "comment_created" else 1
        tension = 0
    elif purpose == "competition":
        valence, intensity = "negative", "medium"
        affinity = -1 if event_type == "comment_created" else -2
        trust = 0
        tension = 1 if event_type == "comment_created" else 2
    elif purpose == "disagreement":
        valence, intensity = "negative", "low"
        affinity = -1
        trust = 0
        tension = 1
    elif purpose in neutral or purpose is None:
        valence, intensity = "neutral", "low"
        affinity = trust = tension = 0
    else:
        raise SocialEventRuntimeError("comment_purpose_invalid")
    return _Delta(
        familiarity=2,
        affinity=affinity,
        trust=trust,
        tension=tension,
        valence=valence,
        intensity=intensity,
    )


def _delta(event_type: str, purpose: str | None) -> _Delta:
    if event_type in {"comment_created", "reply_created", "mention_created"}:
        return _purpose_delta(event_type, purpose)
    return {
        "like_added": _Delta(familiarity=1, affinity=1, valence="positive"),
        "follow_added": _Delta(familiarity=3, affinity=1, valence="positive"),
        "follow_removed": _Delta(affinity=-1, valence="negative"),
        "repost_added": _Delta(familiarity=2, affinity=1, valence="positive"),
        "joint_accepted": _Delta(familiarity=2, trust=1, valence="positive"),
        "joint_completed": _Delta(
            familiarity=4,
            affinity=2,
            trust=3,
            valence="positive",
            intensity="medium",
        ),
    }.get(event_type, _Delta())


def _validate_live_public_post(post: EventPost | None, *, world_id: str) -> None:
    if post is None or post.world_id != world_id:
        raise SocialEventRuntimeError("evidence_post_world_mismatch")
    if post.deleted_at is not None:
        raise SocialEventRuntimeError("evidence_source_deleted")
    if post.report_hidden_at is not None or post.visibility != "public":
        raise SocialEventRuntimeError("evidence_source_hidden")
