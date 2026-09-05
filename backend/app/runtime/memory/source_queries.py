"""Read foreign canonical rows using the Session supplied by Memory."""

from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import hashlib
import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.chat.models import (
    MessageMessage,
    MessageThread,
)
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.relationships.models.social import RelationshipStateChange
from app.domains.relationships.models.social import SocialEvent
from app.domains.relationships.models.social import SocialEventEvidence
from app.domains.routines.models import (
    ActivityBeat,
    JointActivity,
    JointActivityParticipant,
)
from app.domains.social.models.posts import Post, PostLike
from app.domains.social.models.feed import WorldCharacterBlock, WorldCharacterFeedObservation
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership


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
    Post = Post
    PostLike = PostLike
    WorldCharacter = WorldCharacter
    WorldCharacterBlock = WorldCharacterBlock
    WorldCharacterFeedObservation = (
        WorldCharacterFeedObservation
    )
    WorldMembership = WorldMembership


models = _MemorySourceModels()


def chat_message_pair(session, message_id):
    return session.execute(
        select(models.MessageMessage, models.MessageThread)
        .join(
            models.MessageThread,
            models.MessageThread.id == models.MessageMessage.thread_id,
        )
        .where(models.MessageMessage.id == message_id)
    )


def post_row(session, source_id):
    return session.get(models.Post, source_id)


def reply_parent(session, post):
    return session.get(models.Post, post.reply_to_post_id)


def reaction_row(session, reaction_id):
    return session.get(models.PostLike, reaction_id)


def reaction_post(session, reaction):
    return session.get(models.Post, reaction.post_id)


def social_event_row(session, source_id):
    return session.get(models.SocialEvent, source_id)


def activity_beat_row(session, source_id):
    return session.get(models.ActivityBeat, source_id)


def relationship_change_row(session, source_id):
    return session.get(models.RelationshipStateChange, source_id)


def relationship_social_event(session, change):
    return session.get(models.SocialEvent, change.social_event_id)


def joint_activity_row(session, source_id):
    return session.get(models.JointActivity, source_id)


def joint_participants(session, joint):
    return session.scalars(
        select(models.JointActivityParticipant).where(
            models.JointActivityParticipant.joint_activity_id == joint.id,
            models.JointActivityParticipant.world_id == joint.world_id,
        )
    )


def post_observation(session, scope, post):
    return session.scalar(
        select(models.WorldCharacterFeedObservation).where(
            models.WorldCharacterFeedObservation.world_id == scope.world_id,
            models.WorldCharacterFeedObservation.observer_world_character_id
            == scope.subject_world_character_id,
            models.WorldCharacterFeedObservation.post_id == post.id,
            models.WorldCharacterFeedObservation.status == "observed",
            models.WorldCharacterFeedObservation.observed_at.is_not(None),
        )
    )


def event_post_ids(session, event_id):
    return session.scalars(
        select(models.SocialEventEvidence.source_post_id).where(
            models.SocialEventEvidence.social_event_id == event_id,
            models.SocialEventEvidence.source_post_id.is_not(None),
        )
    )


def event_observation(session, source_post_ids, scope):
    return session.scalar(
        select(models.WorldCharacterFeedObservation.id).where(
            models.WorldCharacterFeedObservation.world_id == scope.world_id,
            models.WorldCharacterFeedObservation.observer_world_character_id
            == scope.subject_world_character_id,
            models.WorldCharacterFeedObservation.post_id.in_(source_post_ids),
            models.WorldCharacterFeedObservation.status == "observed",
            models.WorldCharacterFeedObservation.observed_at.is_not(None),
        )
    )


def active_participant_ids(session, ids, world_id):
    return session.scalars(
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


def block_id(session, world_id, subject, counterpart):
    return session.scalar(
        select(models.WorldCharacterBlock.id).where(
            models.WorldCharacterBlock.world_id == world_id,
            or_(
                (models.WorldCharacterBlock.blocker_world_character_id == subject)
                & (
                    models.WorldCharacterBlock.blocked_world_character_id == counterpart
                ),
                (models.WorldCharacterBlock.blocker_world_character_id == counterpart)
                & (models.WorldCharacterBlock.blocked_world_character_id == subject),
            ),
        )
    )


def read_subjective_source(session, scope, *, source_type, source_id):
    # Keep the original lazy import and original cross-owner query placement.
    from app.runtime.memory.subjective_source import read_subjective_source as read

    return read(session, scope, source_type=source_type, source_id=source_id)
