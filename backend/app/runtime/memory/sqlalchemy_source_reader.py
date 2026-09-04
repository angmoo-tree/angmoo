"""Runtime SQLAlchemy composition for eligible canonical Memory evidence."""

from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import hashlib
import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.chat.infrastructure.sqlalchemy_models import (
    MessageMessage,
    MessageThread,
)
from app.domains.memory.public import (
    CanonicalMemoryEvidence,
    MemoryScope,
    MemorySourceTypeV1,
)
from app.domains.relationships.infrastructure.sqlalchemy_social_models import (
    RelationshipStateChange,
    SocialEvent,
    SocialEventEvidence,
)
from app.domains.routines.infrastructure.sqlalchemy_models import (
    ActivityBeat,
    JointActivity,
    JointActivityParticipant,
)
from app.runtime.social.sqlalchemy_read_repository import (
    social_persistence_models,
)


class _MemorySourceModels:
    """Concrete runtime bindings kept above the Memory domain boundary."""

    ActivityBeat = ActivityBeat
    JointActivity = JointActivity
    JointActivityParticipant = JointActivityParticipant
    MessageMessage = MessageMessage
    MessageThread = MessageThread
    RelationshipStateChange = RelationshipStateChange
    SocialEvent = SocialEvent
    SocialEventEvidence = SocialEventEvidence
    Post = social_persistence_models.Post
    PostLike = social_persistence_models.PostLike
    WorldCharacter = social_persistence_models.WorldCharacter
    WorldCharacterBlock = social_persistence_models.WorldCharacterBlock
    WorldCharacterFeedObservation = (
        social_persistence_models.WorldCharacterFeedObservation
    )
    WorldMembership = social_persistence_models.WorldMembership


models = _MemorySourceModels()


class SqlAlchemyMemorySourceEvidenceReader:
    """Translate canonical rows into a bounded eligibility snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def read_evidence(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        readers = {
            MemorySourceTypeV1.CHAT_MESSAGE: self._read_chat_message,
            MemorySourceTypeV1.OWNER_MEMORY_REQUEST: self._read_chat_message,
            MemorySourceTypeV1.POST: self._read_post,
            MemorySourceTypeV1.REPLY: self._read_post,
            MemorySourceTypeV1.REACTION: self._read_reaction,
            MemorySourceTypeV1.SOCIAL_EVENT: self._read_social_event,
            MemorySourceTypeV1.ACTIVITY_EVENT: self._read_activity_event,
            MemorySourceTypeV1.RELATIONSHIP_EVENT: self._read_relationship_event,
            MemorySourceTypeV1.JOINT_COMMITMENT: self._read_joint_commitment,
        }
        evidence = readers[source_type](scope, source_type, source_id)
        if (
            evidence is None
            or evidence.actor_world_character_id != scope.subject_world_character_id
            or not evidence.successful
        ):
            return evidence
        from app.runtime.memory.subjective_source import read_subjective_source

        subjective = read_subjective_source(
            self._session, scope, source_type=source_type.value, source_id=source_id
        )
        if subjective is None:
            return evidence
        digest, context = subjective
        return replace(
            evidence,
            source_digest=_digest(
                {"canonical": evidence.source_digest, "subjective": digest}
            ),
            subjective_context=context,
        )

    def _read_chat_message(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        try:
            message_id = int(source_id)
        except ValueError:
            return None
        pair = self._session.execute(
            select(models.MessageMessage, models.MessageThread)
            .join(
                models.MessageThread,
                models.MessageThread.id == models.MessageMessage.thread_id,
            )
            .where(models.MessageMessage.id == message_id)
        ).one_or_none()
        if pair is None:
            return None
        message, thread = pair
        if message.role == "assistant":
            actor = thread.responding_world_character_id
            target = thread.requester_world_character_id
        elif message.role == "user":
            actor = thread.requester_world_character_id
            target = thread.responding_world_character_id
        else:
            actor = None
            target = None
        counterpart = _counterpart(scope.subject_world_character_id, actor, target)
        explicit_owner_request = (
            source_type is not MemorySourceTypeV1.OWNER_MEMORY_REQUEST
            or message.role == "user"
        )
        successful = (
            message.status == "ok"
            and thread.world_scope_status == "resolved"
            and explicit_owner_request
        )
        visible = thread.requester_id == scope.owner_id and thread.deleted_at is None
        observed = scope.subject_world_character_id in {actor, target}
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=thread.world_id or "",
            created_at=message.created_at,
            summary=message.content,
            digest_payload={
                "thread_id": thread.id,
                "message_id": message.id,
                "role": message.role,
                "content": message.content,
                "status": message.status,
                "world_scope_status": thread.world_scope_status,
                "deleted_at": thread.deleted_at,
            },
            successful=successful,
            visible=visible,
            observed=observed,
            actor=actor,
            target=target,
            counterpart=counterpart,
            thread_id=thread.id,
        )

    def _read_post(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        post = self._session.get(models.Post, source_id)
        if post is None:
            return None
        is_reply = post.reply_to_post_id is not None
        source_shape_ok = (
            source_type is MemorySourceTypeV1.REPLY
            if is_reply
            else source_type is MemorySourceTypeV1.POST
        )
        target = None
        if post.reply_to_post_id:
            parent = self._session.get(models.Post, post.reply_to_post_id)
            if parent is not None:
                target = parent.author_world_character_id
        actor = post.author_world_character_id
        counterpart = _counterpart(scope.subject_world_character_id, actor, target)
        if counterpart is None and actor != scope.subject_world_character_id:
            counterpart = actor
        observation_id, observed = self._post_observation(
            scope=scope,
            post=post,
            actor=actor,
        )
        visible = post.deleted_at is None and post.report_hidden_at is None
        summary = " ".join(part for part in (post.title, post.body) if part)
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=post.world_id or "",
            created_at=post.created_at,
            summary=summary,
            digest_payload={
                "id": post.id,
                "world_id": post.world_id,
                "author_world_character_id": actor,
                "reply_to_post_id": post.reply_to_post_id,
                "visibility": post.visibility,
                "title": post.title,
                "body": post.body,
                "report_hidden_at": post.report_hidden_at,
                "deleted_at": post.deleted_at,
            },
            successful=source_shape_ok,
            visible=visible,
            observed=observed,
            actor=actor,
            target=target,
            observation_id=observation_id,
            source_event_id=None,
            counterpart=counterpart,
        )

    def _read_reaction(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        try:
            reaction_id = int(source_id)
        except ValueError:
            return None
        reaction = self._session.get(models.PostLike, reaction_id)
        if reaction is None:
            return None
        post = self._session.get(models.Post, reaction.post_id)
        if post is None:
            return None
        actor = reaction.actor_world_character_id
        target = reaction.target_world_character_id
        counterpart = _counterpart(scope.subject_world_character_id, actor, target)
        observation_id, post_observed = self._post_observation(
            scope=scope,
            post=post,
            actor=actor,
        )
        observed = scope.subject_world_character_id == actor or post_observed
        visible = post.deleted_at is None and post.report_hidden_at is None
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=reaction.world_id or "",
            created_at=reaction.created_at,
            summary=f"{actor or 'unknown'} liked {post.title or post.body}",
            digest_payload={
                "id": reaction.id,
                "post_id": reaction.post_id,
                "world_id": reaction.world_id,
                "actor": actor,
                "target": target,
                "post_deleted_at": post.deleted_at,
                "post_report_hidden_at": post.report_hidden_at,
            },
            successful=reaction.world_id is not None,
            visible=visible,
            observed=observed,
            actor=actor,
            target=target,
            observation_id=observation_id,
            counterpart=counterpart,
        )

    def _read_social_event(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        event = self._session.get(models.SocialEvent, source_id)
        if event is None:
            return None
        actor = event.actor_world_character_id
        target = event.target_world_character_id
        counterpart = _counterpart(scope.subject_world_character_id, actor, target)
        observation_id = self._social_event_observation(scope, event.id)
        observed = scope.subject_world_character_id in {actor, target}
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=event.world_id,
            created_at=event.occurred_at,
            summary=f"{event.event_type}: {actor} -> {target or 'world'}",
            digest_payload={
                "id": event.id,
                "world_id": event.world_id,
                "actor": actor,
                "target": target,
                "event_type": event.event_type,
                "result": event.result,
                "retrieval_status": event.retrieval_status,
                "invalidated_at": event.invalidated_at,
                "invalidation_reason": event.invalidation_reason,
            },
            successful=event.result == "succeeded",
            visible=(
                event.retrieval_status == "eligible" and event.invalidated_at is None
            ),
            observed=observed,
            actor=actor,
            target=target,
            observation_id=observation_id,
            source_event_id=event.id,
            counterpart=counterpart,
        )

    def _read_activity_event(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        beat = self._session.get(models.ActivityBeat, source_id)
        if beat is None:
            return None
        summary = _structured_text(beat.result_snapshot or beat.state_after_snapshot)
        source_event_id = beat.source_event_ids[0] if beat.source_event_ids else None
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=beat.world_id,
            created_at=beat.completed_at or beat.created_at,
            summary=summary or f"activity beat {beat.sequence_no} completed",
            digest_payload={
                "id": beat.id,
                "world_id": beat.world_id,
                "world_character_id": beat.world_character_id,
                "episode_id": beat.episode_id,
                "status": beat.status,
                "result_snapshot": beat.result_snapshot,
                "source_event_ids": beat.source_event_ids,
            },
            successful=beat.status == "succeeded" and beat.completed_at is not None,
            visible=True,
            observed=scope.subject_world_character_id == beat.world_character_id,
            actor=beat.world_character_id,
            target=None,
            source_event_id=source_event_id,
            counterpart=None,
        )

    def _read_relationship_event(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        change = self._session.get(models.RelationshipStateChange, source_id)
        if change is None:
            return None
        event = self._session.get(models.SocialEvent, change.social_event_id)
        if event is None:
            return None
        observation_id = self._social_event_observation(scope, event.id)
        actor = change.actor_world_character_id
        target = change.target_world_character_id
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=change.world_id,
            created_at=change.created_at,
            summary=(
                f"relationship {change.valence}/{change.intensity}: {actor} -> {target}"
            ),
            digest_payload={
                "id": change.id,
                "social_event_id": change.social_event_id,
                "world_id": change.world_id,
                "actor": actor,
                "target": target,
                "valence": change.valence,
                "intensity": change.intensity,
                "applied": change.applied,
                "event_retrieval_status": event.retrieval_status,
                "event_invalidated_at": event.invalidated_at,
            },
            successful=(
                change.applied
                and event.result == "succeeded"
                and event.retrieval_status == "eligible"
            ),
            visible=event.invalidated_at is None,
            observed=(
                scope.subject_world_character_id == actor and observation_id is not None
            ),
            actor=actor,
            target=target,
            observation_id=observation_id,
            source_event_id=event.id,
            counterpart=target if scope.subject_world_character_id == actor else None,
        )

    def _read_joint_commitment(
        self,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None:
        joint = self._session.get(models.JointActivity, source_id)
        if joint is None:
            return None
        participants = list(
            self._session.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id == joint.id,
                    models.JointActivityParticipant.world_id == joint.world_id,
                )
            )
        )
        participant_ids = [row.world_character_id for row in participants]
        counterpart = next(
            (
                value
                for value in participant_ids
                if value != scope.subject_world_character_id
            ),
            None,
        )
        accepted = all(
            row.participation_status
            in {"accepted", "scheduled", "active", "consumed", "completed"}
            for row in participants
        )
        scheduled = (
            joint.scheduled_start_at is not None
            and joint.scheduled_end_at is not None
            and joint.status
            in {"scheduled", "ready", "active", "represented", "completed"}
        )
        successful = (
            len(participants) >= 2
            and scope.subject_world_character_id in participant_ids
            and accepted
            and scheduled
            and joint.source_proposal_event_id is not None
            and joint.source_acceptance_event_id is not None
        )
        summary = (
            f"{joint.activity_seed} ({joint.scheduled_start_at.isoformat()} - "
            f"{joint.scheduled_end_at.isoformat()})"
            if scheduled
            else joint.activity_seed
        )
        return self._build(
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            source_world_id=joint.world_id,
            created_at=joint.updated_at,
            summary=summary,
            digest_payload={
                "id": joint.id,
                "world_id": joint.world_id,
                "activity_seed": joint.activity_seed,
                "status": joint.status,
                "scheduled_start_at": joint.scheduled_start_at,
                "scheduled_end_at": joint.scheduled_end_at,
                "source_proposal_event_id": joint.source_proposal_event_id,
                "source_acceptance_event_id": joint.source_acceptance_event_id,
                "participants": sorted(participant_ids),
                "participant_statuses": sorted(
                    (row.world_character_id, row.participation_status)
                    for row in participants
                ),
            },
            successful=successful,
            visible=joint.status not in {"cancelled", "expired", "interrupted"},
            observed=scope.subject_world_character_id in participant_ids,
            actor=scope.subject_world_character_id,
            target=counterpart,
            source_event_id=joint.source_acceptance_event_id,
            counterpart=counterpart,
        )

    def _build(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
        source_world_id: str,
        created_at: datetime,
        summary: str,
        digest_payload: dict[str, Any],
        successful: bool,
        visible: bool,
        observed: bool,
        actor: str | None,
        target: str | None,
        counterpart: str | None,
        observation_id: str | None = None,
        source_event_id: str | None = None,
        thread_id: str | None = None,
    ) -> CanonicalMemoryEvidence:
        membership_active = self._participants_active(
            world_id=source_world_id,
            values=(scope.subject_world_character_id, counterpart),
        )
        blocked = self._blocked(
            world_id=source_world_id,
            subject=scope.subject_world_character_id,
            counterpart=counterpart,
        )
        return CanonicalMemoryEvidence(
            source_type=source_type,
            source_id=source_id,
            source_world_id=source_world_id,
            source_digest=_digest(digest_payload),
            source_created_at=created_at,
            deterministic_summary=_bounded_summary(summary),
            successful=successful,
            visible=visible,
            observed_by_subject=observed,
            membership_active=membership_active,
            blocked=blocked,
            actor_world_character_id=actor,
            target_world_character_id=target,
            observation_id=observation_id,
            source_event_id=source_event_id,
            counterpart_world_character_id=counterpart,
            thread_id=thread_id,
        )

    def _post_observation(
        self,
        *,
        scope: MemoryScope,
        post: models.Post,
        actor: str | None,
    ) -> tuple[str | None, bool]:
        if actor == scope.subject_world_character_id:
            return None, True
        row = self._session.scalar(
            select(models.WorldCharacterFeedObservation).where(
                models.WorldCharacterFeedObservation.world_id == scope.world_id,
                models.WorldCharacterFeedObservation.observer_world_character_id
                == scope.subject_world_character_id,
                models.WorldCharacterFeedObservation.post_id == post.id,
                models.WorldCharacterFeedObservation.status == "observed",
                models.WorldCharacterFeedObservation.observed_at.is_not(None),
            )
        )
        return (None, False) if row is None else (row.id, True)

    def _social_event_observation(
        self, scope: MemoryScope, event_id: str
    ) -> str | None:
        source_post_ids = list(
            self._session.scalars(
                select(models.SocialEventEvidence.source_post_id).where(
                    models.SocialEventEvidence.social_event_id == event_id,
                    models.SocialEventEvidence.source_post_id.is_not(None),
                )
            )
        )
        if not source_post_ids:
            return None
        return self._session.scalar(
            select(models.WorldCharacterFeedObservation.id).where(
                models.WorldCharacterFeedObservation.world_id == scope.world_id,
                models.WorldCharacterFeedObservation.observer_world_character_id
                == scope.subject_world_character_id,
                models.WorldCharacterFeedObservation.post_id.in_(source_post_ids),
                models.WorldCharacterFeedObservation.status == "observed",
                models.WorldCharacterFeedObservation.observed_at.is_not(None),
            )
        )

    def _participants_active(
        self,
        *,
        world_id: str,
        values: tuple[str | None, ...],
    ) -> bool:
        ids = {value for value in values if value is not None}
        if not ids or not world_id:
            return False
        active = set(
            self._session.scalars(
                select(models.WorldCharacter.id)
                .join(
                    models.WorldMembership,
                    models.WorldMembership.id == models.WorldCharacter.membership_id,
                )
                .where(
                    models.WorldCharacter.id.in_(ids),
                    models.WorldCharacter.world_id == world_id,
                    models.WorldCharacter.status == "active",
                    models.WorldMembership.status == "active",
                )
            )
        )
        return active == ids

    def _blocked(
        self,
        *,
        world_id: str,
        subject: str,
        counterpart: str | None,
    ) -> bool:
        if counterpart is None or not world_id:
            return False
        return (
            self._session.scalar(
                select(models.WorldCharacterBlock.id).where(
                    models.WorldCharacterBlock.world_id == world_id,
                    or_(
                        (
                            models.WorldCharacterBlock.blocker_world_character_id
                            == subject
                        )
                        & (
                            models.WorldCharacterBlock.blocked_world_character_id
                            == counterpart
                        ),
                        (
                            models.WorldCharacterBlock.blocker_world_character_id
                            == counterpart
                        )
                        & (
                            models.WorldCharacterBlock.blocked_world_character_id
                            == subject
                        ),
                    ),
                )
            )
            is not None
        )


def _counterpart(subject: str, actor: str | None, target: str | None) -> str | None:
    if actor == subject and target != subject:
        return target
    if target == subject and actor != subject:
        return actor
    return None


def _bounded_summary(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized[:2_000]


def _structured_text(value: dict[str, Any] | None) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _digest(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["SqlAlchemyMemorySourceEvidenceReader"]
