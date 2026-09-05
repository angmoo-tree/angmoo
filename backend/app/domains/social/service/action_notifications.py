"""Link generated/incoming notifications and persist explicit no-action decisions."""

from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.contracts.source_writes import SourceWorldCharacter
from app.domains.social.contracts.subjective_persistence import SubjectiveEvent
from app.domains.social.contracts.action_scope import ActionScopeReferences
from app.domains.social.exceptions import LangGraphSocialApplyError
from app.domains.social.service.action_sources import _target_scope


def _link_notifications(
    db: Session,
    *,
    input_notification_id: int | None,
    actor: SourceWorldCharacter,
    target: SourceWorldCharacter,
    source_post: models.Post | None,
    target_post: models.Post | None,
    event: SubjectiveEvent,
    occurred_at: datetime,
    handling_outcome: str,
    joint_activity_id: str | None,
) -> None:
    if input_notification_id is not None:
        incoming = db.get(models.Notification, input_notification_id)
        if incoming is None or incoming.recipient_character_id != actor.character_id:
            raise LangGraphSocialApplyError("source_notification_invalid")
        incoming.world_id = actor.world_id
        incoming.recipient_world_character_id = actor.id
        incoming.actor_world_character_id = target.id
        incoming.read_at = occurred_at
        incoming.handled_at = occurred_at
        incoming.handling_outcome = handling_outcome
    generated = None
    if source_post is not None:
        generated = db.scalar(
            select(models.Notification)
            .where(
                models.Notification.source_post_id == source_post.id,
                models.Notification.recipient_character_id == target.character_id,
                models.Notification.actor_character_id == actor.character_id,
            )
            .order_by(models.Notification.id.desc())
            .limit(1)
        )
    elif target_post is not None:
        generated = db.scalar(
            select(models.Notification)
            .where(
                models.Notification.post_id == target_post.id,
                models.Notification.recipient_character_id == target.character_id,
                models.Notification.actor_character_id == actor.character_id,
            )
            .order_by(models.Notification.id.desc())
            .limit(1)
        )
    if generated is not None:
        generated.world_id = actor.world_id
        generated.recipient_world_character_id = target.id
        generated.actor_world_character_id = actor.id
        generated.source_social_event_id = event.id
        generated.source_joint_activity_id = joint_activity_id


def mark_notification_handled_without_public_action(
    db: Session,
    *,
    references: ActionScopeReferences,
    actor_character_id: str,
    notification_id: int,
    handling_outcome: str,
    occurred_at: datetime,
) -> models.Notification:
    """Persist an explicit inbox no-action decision without creating a social event."""

    if handling_outcome != "LLM_DECIDED_NO_ACTION":
        raise LangGraphSocialApplyError("notification_no_action_outcome_invalid")
    actor = references.active_world_character(character_id=actor_character_id)
    notification = db.get(models.Notification, notification_id)
    if (
        notification is None
        or notification.recipient_character_id != actor.character_id
        or notification.notification_type
        not in {"reply", "mention", "joint_activity_started"}
    ):
        raise LangGraphSocialApplyError("source_notification_invalid")
    if notification.world_id is not None and notification.world_id != actor.world_id:
        raise LangGraphSocialApplyError("source_notification_world_invalid")
    if notification.handled_at is not None:
        if notification.handling_outcome == handling_outcome:
            return notification
        raise LangGraphSocialApplyError("source_notification_already_handled")
    source_post_id = notification.source_post_id or notification.post_id
    if not source_post_id:
        raise LangGraphSocialApplyError("source_notification_post_missing")
    target, _ = _target_scope(
        db,
        references=references,
        actor=actor,
        action_type="reply",
        target_post_id=source_post_id,
        target_character_id=None,
    )
    if (
        notification.actor_character_id is not None
        and notification.actor_character_id != target.character_id
    ):
        raise LangGraphSocialApplyError("source_notification_actor_invalid")
    if (
        notification.actor_world_character_id is not None
        and notification.actor_world_character_id != target.id
    ):
        raise LangGraphSocialApplyError("source_notification_actor_scope_invalid")

    handled_at = occurred_at.astimezone(UTC)
    notification.world_id = actor.world_id
    notification.recipient_world_character_id = actor.id
    notification.actor_world_character_id = target.id
    notification.read_at = handled_at
    notification.handled_at = handled_at
    notification.handling_outcome = handling_outcome
    db.flush()
    return notification


def link_world_feed_notification(
    db: Session,
    *,
    action: str,
    source: object,
    world_id: str,
    actor_character_id: str,
    target_character_id: str,
    actor_world_character_id: str,
    target_world_character_id: str,
    target_post_id: str,
    social_event_id: str,
    proposal_id: str | None,
) -> None:
    notification_type = {
        "comment": "reply",
        "like": "like",
        "repost": "repost",
        "follow": "follow",
    }[action]
    notification_query = select(models.Notification).where(
        models.Notification.notification_type == notification_type,
        models.Notification.recipient_character_id == target_character_id,
        models.Notification.actor_character_id == actor_character_id,
    )
    if isinstance(source, models.Post):
        notification_query = notification_query.where(
            models.Notification.source_post_id == source.id
        )
    elif action in {"like", "repost"}:
        notification_query = notification_query.where(
            models.Notification.post_id == target_post_id
        )
    notification = db.scalar(
        notification_query.order_by(models.Notification.id.desc()).limit(1)
    )
    if notification is not None:
        notification.world_id = world_id
        notification.recipient_world_character_id = target_world_character_id
        notification.actor_world_character_id = actor_world_character_id
        notification.source_social_event_id = social_event_id
        if proposal_id is not None:
            notification.data = (
                '{"kind":"activity_proposal","proposal_id":"' + proposal_id + '"}'
            )
