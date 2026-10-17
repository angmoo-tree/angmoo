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
from app.domains.social.models.feed import WorldCharacterFeedObservation
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
        self.messages, self.threads, self.posts, self.events, self.event_posts = {}, {}, {}, {}, {}
        self.active_cache, self.block_cache, self.observations = {}, {}, {}
        self.event_observation_cache = {}
        self.loaded, self.observation_posts, self.subjective = set(), {}, {}
        self.prepare(session, identities)

    def prepare(self, session, identities, scopes=()):
        pending = set(identities) - self.loaded
        self.messages.update({row.id: row for row in _rows(session, MessageMessage, MessageMessage.id,
            (int(identifier) for kind, identifier in pending if kind in {"CHAT_MESSAGE", "OWNER_MEMORY_REQUEST"} and identifier.isdecimal()))})
        thread_ids = {row.thread_id for row in self.messages.values()} - self.threads.keys()
        self.threads.update((identifier, None) for identifier in thread_ids)
        self.threads.update({row.id: row for row in _rows(session, MessageThread, MessageThread.id, thread_ids)})
        self.posts.update({row.id: row for row in _rows(session, Post, Post.id,
            (identifier for kind, identifier in pending if kind in {"POST", "REPLY"}))})
        parent_ids = {row.reply_to_post_id for row in self.posts.values() if row is not None and row.reply_to_post_id} - self.posts.keys()
        self.posts.update((identifier, None) for identifier in parent_ids)
        self.posts.update({row.id: row for row in _rows(session, Post, Post.id, parent_ids)})
        event_ids = {identifier for kind, identifier in pending if kind == "SOCIAL_EVENT"}
        self.events.update((identifier, None) for identifier in event_ids)
        self.events.update((row.id, row) for row in _rows(session, SocialEvent, SocialEvent.id, event_ids))
        self.event_posts.update((identifier, []) for identifier in event_ids)
        for row in _rows(session, SocialEventEvidence, SocialEventEvidence.social_event_id, event_ids):
            if row.source_post_id is not None:
                self.event_posts[row.social_event_id].append(row.source_post_id)
        self.loaded.update(pending)
        post_ids = set(self.posts) | {identifier for values in self.event_posts.values() for identifier in values}
        for scope in set(scopes):
            missing = post_ids - self.observation_posts.setdefault(scope, set())
            for offset in range(0, len(missing), 400):
                chunk = sorted(missing)[offset:offset + 400]
                rows = session.scalars(select(WorldCharacterFeedObservation).where(
                    WorldCharacterFeedObservation.world_id == scope.world_id,
                    WorldCharacterFeedObservation.observer_world_character_id == scope.subject_world_character_id,
                    WorldCharacterFeedObservation.post_id.in_(chunk),
                    WorldCharacterFeedObservation.status == "observed",
                    WorldCharacterFeedObservation.observed_at.is_not(None)).execution_options(populate_existing=True))
                for identifier in chunk:
                    self.observations[(scope, identifier)] = None
                for row in rows:
                    self.observations[(scope, row.post_id)] = row
            self.observation_posts[scope].update(missing)
            unseen = {(kind, identifier) for kind, identifier in identities
                if (scope, kind, identifier) not in self.subjective}
            from app.runtime.memory.subjective_source_batch import read_subjective_batch
            self.subjective.update(((scope, *identity), value) for identity, value
                in read_subjective_batch(session, scope, unseen).items())

    def social_event_row(self, session, source_id):
        return self.events[source_id] if source_id in self.events else source_queries.social_event_row(session, source_id)

    def event_post_ids(self, session, event_id):
        return self.event_posts[event_id] if event_id in self.event_posts else source_queries.event_post_ids(session, event_id)

    def event_observation(self, session, source_post_ids, scope):
        key = scope, tuple(sorted(set(source_post_ids)))
        if key in self.event_observation_cache:
            return self.event_observation_cache[key]
        if set(source_post_ids) <= self.observation_posts.get(scope, set()):
            found = {row.id for identifier in source_post_ids
                if (row := self.observations.get((scope, identifier))) is not None}
            if len(found) <= 1:
                value = next(iter(found), None)
            else:
                # The original query has no ordering. Preserve its selected
                # proof identity when several observed posts could authorize it.
                value = source_queries.event_observation(session, source_post_ids, scope)
        else:
            value = source_queries.event_observation(session, source_post_ids, scope)
        self.event_observation_cache[key] = value
        return value

    def read_subjective_source(self, session, scope, *, source_type, source_id):
        key = scope, source_type, source_id
        if key not in self.subjective:
            self.subjective[key] = source_queries.read_subjective_source(session, scope, source_type=source_type, source_id=source_id)
        return self.subjective[key]

    def __getattr__(self, name):
        return getattr(source_queries, name)

    def chat_message_pair(self, session, message_id):
        message = self.messages.get(message_id)
        thread = None if message is None else self.threads.get(message.thread_id)
        return _Pair(None if thread is None else (message, thread))

    def post_row(self, session, source_id): return self.posts.get(source_id)
    def reply_parent(self, session, post): return self.posts.get(post.reply_to_post_id)

    def post_observation(self, session, scope, post):
        key = scope, post.id
        if key not in self.observations:
            self.observations[key] = source_queries.post_observation(session, scope, post)
        return self.observations[key]

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

    def validate_situation_source(self, manifest, source, *, now, ancestors=frozenset(), validation=None):
        from app.runtime.memory.situation_sources import SituationSources
        situations = SituationSources(self.session) if validation is None or validation.runtime_sources is None else validation.runtime_sources
        return situations.validate(manifest, source, now=now,
            ancestors=ancestors, validation=validation)

    def prepare_situation_sources(self, contexts, *, validation):
        from app.runtime.memory.situation_source_batch import prepare_sources
        prepare_sources(self.session, contexts, validation=validation, queries_factory=_SourceQueries)

    def read_evidence(self, *, scope, source_type, source_id):
        from app.runtime.memory.source_composition import source_evidence_reader
        return source_evidence_reader(self.session).read_evidence(scope=scope, source_type=source_type, source_id=source_id)

    def read_sources(self, *, scope, identities):
        if len(identities) > 10_000:
            raise ValueError("episode_source_manifest_limit")
        memory_repository(self.session).validate_scope(scope)
        queries = _SourceQueries(self.session, identities)
        queries.prepare(self.session, identities, (scope,))
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
            result[(kind, identifier)] = EpisodeSourceDetail(canonical, text, canonical.actor_world_character_id)
        return result

    def read_situation_sources(self, *, scope, identities, context, entries, now, validation=None):
        if len(identities) > 100 or context.snapshot.scope != scope:
            raise ValueError("situation_source_manifest_invalid")
        result = {}
        for entry in entries:
            identity = entry.source_type, entry.source_id
            if identity not in identities or identity in result:
                continue
            access = self.validate_situation_source(context, entry, now=now, validation=validation)
            if access.state != "available" or access.evidence is None:
                continue
            if entry.source_type in {"POST", "REPLY"}:
                text = (self.session.get(Post, entry.source_id, populate_existing=True) if validation is None else validation.get(Post, entry.source_id)).body
            elif entry.source_type in {"CHAT_MESSAGE", "OWNER_MEMORY_REQUEST"}:
                text = (self.session.get(MessageMessage, int(entry.source_id), populate_existing=True) if validation is None else validation.get(MessageMessage, int(entry.source_id))).content
            else:
                text = access.evidence.deterministic_summary
            result[identity] = EpisodeSourceDetail(access.evidence, text, access.evidence.actor_world_character_id)
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
