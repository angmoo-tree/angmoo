"""Bind relationship writes to actual completed chat and delivered SNS sources."""

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from sqlalchemy import select

from app.domains.chat.models import ChatResponseRequest, MessageMessage, MessageThread
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.event_scope import validate_event_scope
from app.domains.worlds.service.character_entry import get_character_entry_world
from app.domains.social.models.posts import Post
from app.domains.social.models.topics import RecommendationDelivery
from app.domains.social.repository.blocks import world_character_pair_is_blocked
from app.domains.relationships.models.personalization import RelationshipMetricApplication, RelationshipExperienceReceipt
from app.domains.relationships.contracts.metric_interpretation import parse_metric_interpretations
from app.domains.relationships.service.personalized_metrics import ExperiencedSource, stage_experience, apply_staged_experience, interpreted_policy


def post_revision(post):
    return sha256(((post.title or "") + "\n" + (post.body or "")).encode()).hexdigest()


class RuntimeExperienceReferences:
    def __init__(self, db, *, confirmed_posts=None):
        self.db = db
        self.confirmed_posts = confirmed_posts or {}

    def validate(self, source):
        actor = self.db.get(WorldCharacter, source.actor_id)
        if actor is None or actor.control_mode != "autonomous":
            raise ValueError("relationship_subject_not_autonomous")
        from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError
        try:
            for identifier in (source.actor_id, source.target_id):
                validate_event_scope(self.db, world_id=source.world_id, world_character_id=identifier, allow_retained_owner=identifier == source.target_id)
        except WorldCharacterSocialScopeError:
            raise ValueError("relationship_world_scope_changed") from None
        if world_character_pair_is_blocked(self.db, world_id=source.world_id,
                first_world_character_id=source.actor_id, second_world_character_id=source.target_id):
            raise ValueError("relationship_pair_blocked")
        if source.kind == "chat_message":
            message = self.db.get(MessageMessage, int(source.key))
            thread = None if message is None else self.db.get(MessageThread, message.thread_id)
            committed = self.db.scalar(select(ChatResponseRequest.request_id).where(
                ChatResponseRequest.user_message_id == int(source.key), ChatResponseRequest.state == "committed"))
            if (message is None or message.role != "user" or message.status != "ok" or thread is None
                or thread.deleted_at is not None or thread.world_id != source.world_id
                or thread.responding_world_character_id != source.actor_id
                or thread.requester_world_character_id != source.target_id or committed is None
                or sha256(message.content.encode()).hexdigest() != source.revision):
                raise ValueError("relationship_chat_source_invalid")
            target = self.db.get(WorldCharacter, source.target_id)
            if target.control_mode != "owner_controlled" or target.owner_user_id != thread.requester_id:
                raise ValueError("relationship_chat_persona_invalid")
        elif source.kind == "post":
            post = self.db.get(Post, source.key)
            if (post is None or post.world_id != source.world_id or post.author_world_character_id != source.target_id
                or post.deleted_at is not None or post.report_hidden_at is not None or post.visibility != "public"
                or post_revision(post) != source.revision):
                raise ValueError("relationship_post_source_invalid")
            if self.confirmed_posts.get(source.key) != source.revision:
                # The persistent application was staged only after the runtime
                # confirmed delivery. Its immutable receipt is the retry proof.
                receipt = self.db.scalar(select(RelationshipExperienceReceipt.id).where(
                    RelationshipExperienceReceipt.world_id == source.world_id,
                    RelationshipExperienceReceipt.actor_world_character_id == source.actor_id,
                    RelationshipExperienceReceipt.source_kind == "post",
                    RelationshipExperienceReceipt.source_key == source.key,
                    RelationshipExperienceReceipt.source_revision == source.revision))
                if receipt is None:
                    raise ValueError("relationship_post_not_delivered")
        else:
            raise ValueError("relationship_source_kind_invalid")


def stage_chat_metrics(db, *, request_id, raw, now):
    request = db.get(ChatResponseRequest, request_id, populate_existing=True)
    if request is None or request.state != "committed":
        return
    thread = db.get(MessageThread, request.thread_id)
    if thread is None or thread.world_id is None or interpreted_policy(db, thread.world_id) is None:
        return
    message = db.get(MessageMessage, request.user_message_id)
    world = get_character_entry_world(db, thread.world_id)
    source = ExperiencedSource(thread.world_id, thread.responding_world_character_id, thread.requester_world_character_id,
        "chat_message", str(message.id), sha256(message.content.encode()).hexdigest(), message.created_at, now, world.timezone)
    parsed = parse_metric_interpretations(raw, max_targets=1)
    interpretation = None
    if parsed.status == "valid" and parsed.interpretations:
        proposed = parsed.interpretations[0]
        if proposed.target_ref == "counterpart_1" and proposed.new_evidence_refs == ("current_message",):
            interpretation = replace(proposed, target_ref=source.target_id, new_evidence_refs=(source.key,))
    stage_experience(db, references=RuntimeExperienceReferences(db), source=source,
        decision_key=request_id, interpretation=interpretation, metadata_status=parsed.status if not parsed.interpretations or interpretation else "invalid")


def apply_pending_metrics(db, *, world_id, actor_id=None, source_kind=None, limit=100):
    query = select(RelationshipMetricApplication.id).join(RelationshipExperienceReceipt,
        RelationshipExperienceReceipt.id == RelationshipMetricApplication.experience_id).where(
        RelationshipMetricApplication.status == "pending", RelationshipExperienceReceipt.world_id == world_id)
    if source_kind:
        query = query.where(RelationshipExperienceReceipt.source_kind == source_kind)
    if actor_id:
        query = query.where(RelationshipExperienceReceipt.actor_world_character_id == actor_id)
    ids = list(db.scalars(query.order_by(RelationshipMetricApplication.created_at, RelationshipMetricApplication.id).limit(limit)))
    for identifier in ids:
        try:
            with db.begin_nested():
                apply_staged_experience(db, application_id=identifier, references=RuntimeExperienceReferences(db), now=datetime.now(UTC))
        except ValueError:
            row = db.get(RelationshipMetricApplication, identifier)
            row.status = "superseded"
    db.commit()


class RelationshipChatLifecycle:
    """Stage metadata in the same transaction as an ordinary committed answer."""
    def __init__(self, db, delegate):
        self.db, self.delegate = db, delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def finalize(self, fence, payload, *, now):
        result = self.delegate.finalize(fence, payload, now=now)
        # Model metadata is optional. Scope rejection cannot erase a valid reply.
        try:
            with self.db.begin_nested():
                stage_chat_metrics(self.db, request_id=fence.request_id, raw=payload.relationship_metrics, now=now)
        except ValueError:
            pass
        return result


def recover_pending_metrics(session_factory, *, now):
    from app.domains.routines.models.resident import AgentSlot
    with session_factory() as db:
        # A writer still using its captured relationship version finishes first.
        if db.scalar(select(AgentSlot.agent_id).where(AgentSlot.locked_by_run_id.is_not(None),
                AgentSlot.lease_expires_at > now).limit(1)):
            return
        worlds = list(db.scalars(select(RelationshipExperienceReceipt.world_id).join(RelationshipMetricApplication,
            RelationshipMetricApplication.experience_id == RelationshipExperienceReceipt.id).where(
                RelationshipMetricApplication.status == "pending").distinct().limit(20)))
        for world_id in worlds:
            apply_pending_metrics(db, world_id=world_id, limit=100)
