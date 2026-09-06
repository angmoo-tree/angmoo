"""Today SNS action classification and canonical content revision values."""

from datetime import UTC, datetime
from hashlib import sha256
import json
from app.domains.social.contracts.today_activity import TodaySocialActivityKind


def _execution_matches(execution, event):
    return (
        execution is not None
        and execution.status == "succeeded"
        and execution.social_event_id == event.id
        and execution.world_id == event.world_id
        and execution.actor_world_character_id == event.actor_world_character_id
    )


def _event_kind(event, subject_id):
    outgoing = event.actor_world_character_id == subject_id
    if event.event_type == "post_published":
        return TodaySocialActivityKind.POST_AUTHORED if outgoing else None
    if event.event_type in {"reply_created", "comment_created", "joint_proposed"}:
        return (
            TodaySocialActivityKind.REPLY_AUTHORED
            if outgoing
            else TodaySocialActivityKind.REPLY_RECEIVED
        )
    if event.event_type == "mention_created":
        return (
            TodaySocialActivityKind.REPLY_AUTHORED
            if outgoing
            else TodaySocialActivityKind.MENTION_RECEIVED
        )
    if event.event_type in {"like_added", "like_removed"}:
        return (
            TodaySocialActivityKind.REACTION_GIVEN
            if outgoing
            else TodaySocialActivityKind.REACTION_RECEIVED
        )
    if event.event_type in {"repost_added", "repost_removed"}:
        return TodaySocialActivityKind.REPOST
    if event.event_type in {"follow_added", "follow_removed"}:
        return TodaySocialActivityKind.FOLLOW
    return None


def _post_revision(post):
    return _digest(
        {
            "id": post.id,
            "title": post.title,
            "body": post.body,
            "updated_at": _aware(post.updated_at).isoformat(),
        }
    )


def _chain_revision(chain):
    return _digest([_post_revision(post) for post in chain])


def _source_revision(event, evidence, chain, subjective):
    return _digest(
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "occurred_at": _aware(event.occurred_at).isoformat(),
            "evidence_digest": evidence.content_sha256,
            "chain_revision": _chain_revision(chain),
            "subjective_digest": None
            if subjective is None
            else subjective.source_digest,
        }
    )


def _digest(payload):
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _watermark(rows, *, attribute="updated_at"):
    values = []
    for row in rows:
        value = getattr(row, attribute, None)
        if isinstance(value, datetime):
            values.append(_aware(value).isoformat())
        elif isinstance(value, str) and value:
            values.append(value)
        elif isinstance(getattr(row, "occurred_at", None), datetime):
            values.append(_aware(row.occurred_at).isoformat())
    return None if not values else _digest(sorted(values))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
