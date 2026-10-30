"""Operation-local source batching, independent of detail/reader composition."""
from sqlalchemy import select
from app.domains.chat.models import MessageMessage, MessageThread
from app.domains.social.models.posts import Post
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
from app.runtime.memory import source_queries

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
