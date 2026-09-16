"""Canonical original text and own thought loading on the caller's transaction."""

from hashlib import sha256
from sqlalchemy import select

from app.contracts.activity_thought import ActivityThought
from app.domains.chat.models import ChatMessageThought, ChatResponseRequest, MessageMessage, MessageThread
from app.domains.memory.contracts.episode_packet import EpisodeSourceDetail
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.memory.service.source_evidence import SqlAlchemyMemorySourceEvidenceReader
from app.domains.social.models.posts import Post
from app.domains.social.models.activity_thought import SocialActivityThought
from app.domains.social.service.today_activity_thoughts import validated_activity_thoughts
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.runtime.memory import source_queries
from app.runtime.memory.composition import memory_repository


def _rows(session, model, column, values):
    values = tuple(dict.fromkeys(values))
    result = []
    for start in range(0, len(values), 400):
        result.extend(session.scalars(select(model).where(column.in_(values[start:start + 400]))
            .execution_options(populate_existing=True)))
    return result


class _Pair:
    def __init__(self, value): self.value = value
    def one_or_none(self): return self.value


class _SourceQueries:
    def __init__(self, session, identities):
        self.messages = {row.id: row for row in _rows(session, MessageMessage, MessageMessage.id,
            (int(identifier) for kind, identifier in identities if kind in {"CHAT_MESSAGE", "OWNER_MEMORY_REQUEST"} and identifier.isdecimal()))}
        self.threads = {row.id: row for row in _rows(session, MessageThread, MessageThread.id,
            (row.thread_id for row in self.messages.values()))}
        self.posts = {row.id: row for row in _rows(session, Post, Post.id,
            (identifier for kind, identifier in identities if kind in {"POST", "REPLY"}))}
        self.posts.update({row.id: row for row in _rows(session, Post, Post.id,
            (row.reply_to_post_id for row in tuple(self.posts.values()) if row.reply_to_post_id))})
        self.active_cache, self.block_cache = {}, {}

    def __getattr__(self, name):
        return getattr(source_queries, name)

    def chat_message_pair(self, session, message_id):
        message = self.messages.get(message_id)
        thread = None if message is None else self.threads.get(message.thread_id)
        return _Pair(None if thread is None else (message, thread))

    def post_row(self, session, source_id): return self.posts.get(source_id)
    def reply_parent(self, session, post): return self.posts.get(post.reply_to_post_id)

    def active_participant_ids(self, session, ids, world_id):
        key = world_id, frozenset(ids)
        if key not in self.active_cache:
            self.active_cache[key] = tuple(source_queries.active_participant_ids(session, ids, world_id))
        return self.active_cache[key]

    def block_id(self, session, world_id, subject, counterpart):
        key = world_id, subject, counterpart
        if key not in self.block_cache:
            self.block_cache[key] = source_queries.block_id(session, world_id, subject, counterpart)
        return self.block_cache[key]


class RuntimeEpisodeDetailReader:
    def __init__(self, session): self.session = session

    def read_sources(self, *, scope, identities):
        if len(identities) > 10_000:
            raise ValueError("episode_source_manifest_limit")
        memory_repository(self.session).validate_scope(scope)
        queries = _SourceQueries(self.session, identities)
        reader = SqlAlchemyMemorySourceEvidenceReader(self.session, queries=queries)
        result = {}
        for kind, identifier in identities:
            source_type = MemorySourceTypeV1(kind)
            canonical = reader.read_evidence(scope=scope, source_type=source_type, source_id=identifier)
            if canonical is None:
                continue
            blocked = memory_evidence_blocked_code(scope=scope, source_type=source_type, source_id=identifier, evidence=canonical)
            if blocked:
                result[(kind, identifier)] = EpisodeSourceDetail(canonical, "")
                continue
            if kind in {"CHAT_MESSAGE", "OWNER_MEMORY_REQUEST"}:
                text = queries.messages[int(identifier)].content
            elif kind in {"POST", "REPLY"}:
                post = queries.posts[identifier]
                text = "\n".join(part for part in (post.title, post.body) if part)
            else:
                # Non-text activities are typed canonical execution records.
                text = canonical.deterministic_summary
            result[(kind, identifier)] = EpisodeSourceDetail(canonical, text)
        return result

    def read_thoughts(self, *, scope, references):
        if len(references) > 2_750:
            raise ValueError("episode_thought_manifest_limit")
        memory_repository(self.session).validate_scope(scope)
        result = {}
        chat_ids = [int(ref[5:]) for ref in references if ref.startswith("chat:") and ref[5:].isdecimal()]
        for start in range(0, len(chat_ids), 400):
            rows = self.session.execute(select(ChatMessageThought, MessageMessage).join(
                MessageMessage, MessageMessage.id == ChatMessageThought.message_id,
            ).join(MessageThread, MessageThread.id == MessageMessage.thread_id).join(
                ChatResponseRequest, ChatResponseRequest.request_id == ChatMessageThought.request_id,
            ).where(ChatMessageThought.message_id.in_(chat_ids[start:start + 400]),
                MessageThread.requester_id == scope.owner_id, MessageThread.world_id == scope.world_id,
                MessageThread.responding_world_character_id == scope.subject_world_character_id,
                MessageThread.world_scope_status == "resolved", MessageThread.deleted_at.is_(None),
                ChatResponseRequest.thread_id == MessageThread.id, ChatResponseRequest.state == "committed",
                ChatResponseRequest.committed_assistant_message_id == MessageMessage.id,
                MessageMessage.role == "assistant", MessageMessage.status == "ok")
                .execution_options(populate_existing=True)).all()
            for thought, message in rows:
                result[f"chat:{message.id}"] = ActivityThought(status="invalid") if (
                    thought.source_digest != sha256(message.content.encode()).hexdigest()
                ) else ActivityThought(thought.thought_text, thought.status, thought.truncated)
        social_ids = [ref[7:] for ref in references if ref.startswith("social:")]
        rows = [row for row in _rows(self.session, SocialActivityThought, SocialActivityThought.id, social_ids)
                if row.owner_id == scope.owner_id and row.world_id == scope.world_id
                and row.actor_world_character_id == scope.subject_world_character_id]
        events = _rows(self.session, SocialEvent, SocialEvent.id, (row.social_event_id for row in rows))
        evidences = _rows(self.session, SocialEventEvidence, SocialEventEvidence.social_event_id, (row.social_event_id for row in rows))
        # Select the exact execution evidence, not an arbitrary observation receipt.
        expected_executions = {(row.social_event_id, row.public_action_execution_id) for row in rows}
        by_event = {row.social_event_id: row for row in evidences
                    if (row.social_event_id, row.public_action_execution_id) in expected_executions}
        executions = {row.id: row for row in _rows(self.session, AgentPublicActionExecution, AgentPublicActionExecution.id,
            (row.public_action_execution_id for row in rows if row.public_action_execution_id is not None))}
        posts = {row.id: row for row in _rows(self.session, Post, Post.id, (row.source_post_id for row in rows if row.source_post_id))}
        validated = validated_activity_thoughts(rows, owner_id=scope.owner_id, world_id=scope.world_id,
            subject_id=scope.subject_world_character_id, events=events, evidence_by_event=by_event,
            executions=executions, posts=posts)
        result.update({f"social:{record.thought_id}": record.thought for record in validated.values()})
        return result
