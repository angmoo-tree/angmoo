from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)
from app.services import activity_proposal_runtime


class LangGraphSocialApplyError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ProposalResponseInput:
    proposal_id: str
    decision: str
    counter_activity_seed: str | None = None
    counter_place_key: str | None = None
    counter_target_daypart: str | None = None
    counter_date_policy: str | None = None
    counter_target_date: date | None = None


@dataclass(frozen=True)
class PreparedProposalResponse:
    proposal: models.ActivityProposal
    response: ProposalResponseInput
    resolved_schedule: activity_proposal_runtime.ResolvedSchedule | None


@dataclass(frozen=True)
class LangGraphSocialApplyResult:
    event: models.SocialEvent
    proposal_result: activity_proposal_runtime.ProposalResponseResult | None


def active_world_character(
    db: Session, *, character_id: str
) -> models.WorldCharacter:
    active = db.get(models.CharacterActiveWorld, character_id)
    if active is None:
        raise LangGraphSocialApplyError("active_world_required")
    world_character = db.get(models.WorldCharacter, active.world_character_id)
    if (
        world_character is None
        or world_character.character_id != character_id
        or world_character.status != "active"
    ):
        raise LangGraphSocialApplyError("active_world_character_invalid")
    return world_character


def _world_character_for_character(
    db: Session,
    *,
    world_id: str,
    character_id: str,
) -> models.WorldCharacter:
    world_character = db.scalar(
        select(models.WorldCharacter).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character_id,
            models.WorldCharacter.status == "active",
        )
    )
    if world_character is None:
        raise LangGraphSocialApplyError("target_world_character_invalid")
    return world_character


def _root_post_id(db: Session, post: models.Post) -> str:
    current = post
    seen = {post.id}
    for _ in range(20):
        parent_id = current.reply_to_post_id
        if not parent_id:
            return current.id
        if parent_id in seen:
            raise LangGraphSocialApplyError("post_reply_cycle")
        seen.add(parent_id)
        parent = db.get(models.Post, parent_id)
        if parent is None or parent.world_id != post.world_id:
            raise LangGraphSocialApplyError("post_root_invalid")
        current = parent
    raise LangGraphSocialApplyError("post_reply_depth_exceeded")


def proposal_for_notification(
    db: Session,
    *,
    recipient_character_id: str,
    source_post_id: str,
) -> models.ActivityProposal | None:
    try:
        world_character = active_world_character(
            db, character_id=recipient_character_id
        )
    except LangGraphSocialApplyError:
        return None
    source = db.get(models.Post, source_post_id)
    if source is None or source.world_id != world_character.world_id:
        return None
    return activity_proposal_runtime.find_open_proposal_for_source_post(
        db,
        world_id=world_character.world_id,
        target_world_character_id=world_character.id,
        source_post_id=source_post_id,
    )


def prepare_proposal_response(
    db: Session,
    *,
    character_id: str,
    response: ProposalResponseInput,
    now: datetime,
) -> PreparedProposalResponse:
    actor = active_world_character(db, character_id=character_id)
    proposal = db.get(models.ActivityProposal, response.proposal_id)
    if (
        proposal is None
        or proposal.status != "proposed"
        or proposal.world_id != actor.world_id
        or proposal.target_world_character_id != actor.id
    ):
        raise LangGraphSocialApplyError("proposal_response_not_allowed")
    if response.decision not in {"accept", "reject", "counter"}:
        raise LangGraphSocialApplyError("proposal_decision_invalid")
    resolved = None
    if response.decision == "accept":
        resolved = activity_proposal_runtime.resolve_acceptance_schedule(
            db, proposal_id=proposal.id, now=now
        )
    elif response.decision == "counter":
        if (
            not response.counter_activity_seed
            or response.counter_target_daypart
            not in {"dawn", "morning", "afternoon", "evening"}
            or response.counter_date_policy not in {"exact", "earliest_available"}
            or (
                response.counter_date_policy == "exact"
                and response.counter_target_date is None
            )
        ):
            raise LangGraphSocialApplyError("proposal_counter_invalid")
    return PreparedProposalResponse(proposal, response, resolved)


def _target_scope(
    db: Session,
    *,
    actor: models.WorldCharacter,
    action_type: str,
    target_post_id: str | None,
    target_character_id: str | None,
) -> tuple[models.WorldCharacter, models.Post | None]:
    if target_post_id is not None:
        post = db.get(models.Post, target_post_id)
        if (
            post is None
            or post.world_id != actor.world_id
            or post.author_character_id is None
            or post.author_world_character_id is None
        ):
            raise LangGraphSocialApplyError("target_post_world_invalid")
        target = db.get(models.WorldCharacter, post.author_world_character_id)
        if (
            target is None
            or target.world_id != actor.world_id
            or target.character_id != post.author_character_id
        ):
            raise LangGraphSocialApplyError("target_post_author_invalid")
        return target, post
    if action_type not in {"follow", "unfollow"} or not target_character_id:
        raise LangGraphSocialApplyError("target_world_character_required")
    return (
        _world_character_for_character(
            db,
            world_id=actor.world_id,
            character_id=target_character_id,
        ),
        None,
    )


def _source_evidence(
    db: Session,
    *,
    action_type: str,
    actor: models.WorldCharacter,
    target: models.WorldCharacter,
    target_post: models.Post | None,
    action_result: dict[str, object],
    execution: models.AgentPublicActionExecution,
) -> tuple[object, str, str, str, models.Post | None]:
    if action_type == "reply":
        reply_id = str(action_result.get("post_id") or "")
        row = db.get(models.Post, reply_id)
        if (
            row is None
            or target_post is None
            or row.reply_to_post_id != target_post.id
            or row.world_id != actor.world_id
            or row.author_world_character_id != actor.id
        ):
            raise LangGraphSocialApplyError("reply_evidence_missing")
        return row, "reply_post", "post", row.id, row
    if action_type == "like":
        if target_post is None:
            raise LangGraphSocialApplyError("like_target_missing")
        row = db.scalar(
            select(models.PostLike).where(
                models.PostLike.post_id == target_post.id,
                models.PostLike.character_id == actor.character_id,
            )
        )
        if row is None:
            raise LangGraphSocialApplyError("like_evidence_missing")
        row.world_id = actor.world_id
        row.actor_world_character_id = actor.id
        row.target_world_character_id = target.id
        return row, "like", "post_like", str(row.id), None
    if action_type == "repost":
        if target_post is None:
            raise LangGraphSocialApplyError("repost_target_missing")
        row = db.scalar(
            select(models.PostRepost).where(
                models.PostRepost.post_id == target_post.id,
                models.PostRepost.character_id == actor.character_id,
            )
        )
        if row is None:
            raise LangGraphSocialApplyError("repost_evidence_missing")
        row.world_id = actor.world_id
        row.actor_world_character_id = actor.id
        row.target_world_character_id = target.id
        return row, "repost", "post_repost", str(row.id), None
    if action_type == "follow":
        row = db.scalar(
            select(models.ProfileFollow).where(
                models.ProfileFollow.follower_character_id == actor.character_id,
                models.ProfileFollow.target_character_id == target.character_id,
            )
        )
        if row is None:
            raise LangGraphSocialApplyError("follow_evidence_missing")
        row.world_id = actor.world_id
        row.follower_world_character_id = actor.id
        row.target_world_character_id = target.id
        return row, "follow", "profile_follow", str(row.id), None
    if action_type == "unfollow":
        execution.world_id = actor.world_id
        execution.actor_world_character_id = actor.id
        db.flush()
        return (
            execution,
            "execution",
            "agent_public_action_execution",
            str(execution.id),
            None,
        )
    raise LangGraphSocialApplyError("unsupported_public_action")


def _event_type(
    action_type: str, proposal_response: PreparedProposalResponse | None
) -> str:
    if proposal_response is not None:
        return {
            "accept": "joint_accepted",
            "reject": "joint_declined",
            "counter": "joint_proposed",
        }[proposal_response.response.decision]
    return {
        "reply": "reply_created",
        "like": "like_added",
        "repost": "repost_added",
        "follow": "follow_added",
        "unfollow": "follow_removed",
    }[action_type]


def _link_notifications(
    db: Session,
    *,
    input_notification_id: int | None,
    actor: models.WorldCharacter,
    target: models.WorldCharacter,
    source_post: models.Post | None,
    target_post: models.Post | None,
    event: models.SocialEvent,
    occurred_at: datetime,
    handling_outcome: str,
    joint_activity_id: str | None,
) -> None:
    if input_notification_id is not None:
        incoming = db.get(models.Notification, input_notification_id)
        if (
            incoming is None
            or incoming.recipient_character_id != actor.character_id
        ):
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


def apply_successful_public_action(
    db: Session,
    *,
    actor_character_id: str,
    action_type: str,
    target_post_id: str | None,
    target_character_id: str | None,
    action_result: dict[str, object],
    execution: models.AgentPublicActionExecution,
    occurred_at: datetime,
    notification_id: int | None = None,
    source_text: str | None = None,
    proposal_response: PreparedProposalResponse | None = None,
) -> LangGraphSocialApplyResult:
    actor = active_world_character(db, character_id=actor_character_id)
    target, target_post = _target_scope(
        db,
        actor=actor,
        action_type=action_type,
        target_post_id=target_post_id,
        target_character_id=target_character_id,
    )
    if proposal_response is not None:
        proposal = proposal_response.proposal
        if (
            action_type != "reply"
            or proposal.world_id != actor.world_id
            or proposal.target_world_character_id != actor.id
            or proposal.proposer_world_character_id != target.id
        ):
            raise LangGraphSocialApplyError("proposal_response_scope_invalid")
    source, evidence_kind, source_type, source_id, source_post = _source_evidence(
        db,
        action_type=action_type,
        actor=actor,
        target=target,
        target_post=target_post,
        action_result=action_result,
        execution=execution,
    )
    execution.world_id = actor.world_id
    execution.actor_world_character_id = actor.id
    execution.interaction_intent = (
        "proposal_response" if proposal_response is not None else execution.interaction_intent
    )
    db.flush()

    event_type = _event_type(action_type, proposal_response)
    root_post_id = _root_post_id(db, target_post) if target_post is not None else None
    event = social_event_runtime.record_successful_social_event(
        db,
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        target_world_character_id=target.id,
        event_type=event_type,
        occurred_at=occurred_at,
        idempotency_key=sha256(
            f"langgraph|{execution.signature}|{event_type}".encode("utf-8")
        ).hexdigest(),
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind=evidence_kind,
            source_object_type=source_type,
            source_object_id=source_id,
            root_post_id=root_post_id,
            source_post_id=(source_post.id if source_post is not None else target_post_id),
            target_post_id=target_post_id,
            source_notification_id=notification_id,
            agent_run_id=execution.run_id,
            public_action_execution_id=execution.id,
            interaction_intent=execution.interaction_intent,
            comment_purpose=execution.comment_purpose,
            proposal_decision=(
                proposal_response.response.decision
                if proposal_response is not None
                else None
            ),
            source_text=source_text,
            source_visibility_at_event=("public" if target_post is not None else "not_applicable"),
            source_author_id_at_event=target.id,
        ),
    ).event
    execution.social_event_id = event.id

    proposal_result = None
    if proposal_response is not None:
        response = proposal_response.response
        proposal_result = activity_proposal_runtime.apply_response(
            db,
            proposal_id=proposal_response.proposal.id,
            response_event=event,
            decision=response.decision,
            now=occurred_at,
            resolved_schedule=proposal_response.resolved_schedule,
            counter_activity_seed=response.counter_activity_seed,
            counter_place_key=response.counter_place_key,
            counter_target_daypart=response.counter_target_daypart,
            counter_date_policy=response.counter_date_policy,
            counter_target_date=response.counter_target_date,
        )
        action_result["proposal_id"] = proposal_result.proposal.id
        if proposal_result.child_proposal is not None:
            action_result["counter_proposal_id"] = proposal_result.child_proposal.id
        if proposal_result.joint_activity is not None:
            action_result["joint_activity_id"] = proposal_result.joint_activity.id

    action_result["social_event_id"] = event.id
    _link_notifications(
        db,
        input_notification_id=notification_id,
        actor=actor,
        target=target,
        source_post=source_post,
        target_post=target_post,
        event=event,
        occurred_at=occurred_at.astimezone(UTC),
        handling_outcome=(
            f"proposal_{proposal_response.response.decision}"
            if proposal_response is not None
            else action_type
        ),
        joint_activity_id=(
            proposal_result.joint_activity.id
            if proposal_result is not None
            and proposal_result.joint_activity is not None
            else None
        ),
    )
    db.flush()
    return LangGraphSocialApplyResult(event, proposal_result)


def mark_notification_handled_without_public_action(
    db: Session,
    *,
    actor_character_id: str,
    notification_id: int,
    handling_outcome: str,
    occurred_at: datetime,
) -> models.Notification:
    """Persist an explicit inbox no-action decision without creating a social event."""

    if handling_outcome != "LLM_DECIDED_NO_ACTION":
        raise LangGraphSocialApplyError("notification_no_action_outcome_invalid")
    actor = active_world_character(db, character_id=actor_character_id)
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
