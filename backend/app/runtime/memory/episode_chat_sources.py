"""Compose committed Chat turns with Memory's unchanged canonical validation.

Only one bounded thread page is held at a time. This reader does not claim or
mark work processed; the caller's epoch/cutoff and atomic apply own progress.
"""

from dataclasses import asdict, dataclass
from datetime import UTC
from hashlib import sha256
import json

from sqlalchemy import or_, select

from app.domains.chat.models import MessageMessage, MessageThread
from app.domains.chat.repository.memory_turns import SqlAlchemyChatMemoryTurns
from app.domains.memory.contracts.episode import EpisodeSourceMember, EpisodeSourceUnit
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.memory.service.source_evidence import SqlAlchemyMemorySourceEvidenceReader
from app.domains.social.models.feed import WorldCharacterBlock
from app.runtime.memory import source_queries
from app.runtime.memory.episode_labels import episode_actor_labels


class _OneRow:
    def __init__(self, value):
        self.value = value

    def one_or_none(self):
        return self.value


class _ChatQueries:
    """Read-only page snapshot; never a cache across requests/transactions."""

    def __init__(self, session, scope, turns):
        ids = {mid for turn in turns for mid in (turn.user_message_id, turn.assistant_message_id)}
        rows = session.execute(select(MessageMessage, MessageThread).join(
            MessageThread, MessageThread.id == MessageMessage.thread_id,
        ).where(MessageMessage.id.in_(ids))).all() if ids else ()
        self.pairs = {message.id: (message, thread) for message, thread in rows}
        participant_ids = {identifier for _, thread in rows for identifier in (
            thread.responding_world_character_id, thread.requester_world_character_id,
        ) if identifier}
        self.active = set(source_queries.active_participant_ids(session, participant_ids, scope.world_id))
        subject = scope.subject_world_character_id
        blocks = session.scalars(select(WorldCharacterBlock).where(
            WorldCharacterBlock.world_id == scope.world_id,
            or_(WorldCharacterBlock.blocker_world_character_id == subject,
                WorldCharacterBlock.blocked_world_character_id == subject),
        ))
        self.blocks = {
            frozenset((row.blocker_world_character_id, row.blocked_world_character_id)): row.id
            for row in blocks
        }

    def chat_message_pair(self, session, message_id):
        return _OneRow(self.pairs.get(message_id))

    def active_participant_ids(self, session, ids, world_id):
        return self.active.intersection(ids)

    def block_id(self, session, world_id, subject, counterpart):
        return self.blocks.get(frozenset((subject, counterpart)))

    def read_subjective_source(self, session, scope, *, source_type, source_id):
        # Legacy SNS declarations do not apply to Chat messages. Chat thoughts
        # are separately linked and hashed, never part of legacy evidence text.
        return None


@dataclass(frozen=True, slots=True)
class EpisodeChatPage:
    new_units: tuple[EpisodeSourceUnit, ...]
    context_units: tuple[EpisodeSourceUnit, ...]
    through_sequence: int
    rejected_request_ids: tuple[str, ...]


def read_episode_chat_page(session, *, scope: MemoryScope, thread_id: str,
                           cutoff: int, after: int = 0, assistant_ids=None) -> EpisodeChatPage:
    """At most 50 fresh turns plus the latest five preceding committed turns.

    Rejected sources are reported, not silently declared processed. The caller
    must resolve rejection before advancing its durable processing cursor.
    """
    reader = SqlAlchemyChatMemoryTurns(session)
    arguments = dict(owner_id=scope.owner_id, world_id=scope.world_id,
                     subject_id=scope.subject_world_character_id, thread_id=thread_id)
    fresh = reader.read_page(**arguments, cutoff=cutoff, after=after, limit=50, assistant_ids=assistant_ids)
    context = reader.read_page(**arguments, cutoff=min(after, cutoff), limit=5, latest=True) if after else ()
    queries = _ChatQueries(session, scope, (*context, *fresh))
    labels = episode_actor_labels(session, scope=scope, actor_ids=(
        actor for _, thread in queries.pairs.values()
        for actor in (thread.responding_world_character_id, thread.requester_world_character_id)))
    evidence_reader = SqlAlchemyMemorySourceEvidenceReader(session, queries=queries)
    rejected = []

    def convert(turns):
        units = []
        for turn in turns:
            members = []
            for identifier, role, text in (
                (turn.user_message_id, "user", turn.user_text),
                (turn.assistant_message_id, "assistant", turn.assistant_text),
            ):
                evidence = evidence_reader.read_evidence(
                    scope=scope, source_type=MemorySourceTypeV1.CHAT_MESSAGE, source_id=str(identifier),
                )
                if memory_evidence_blocked_code(evidence=evidence, scope=scope,
                                               source_type=MemorySourceTypeV1.CHAT_MESSAGE,
                                               source_id=str(identifier)):
                    break
                members.append(EpisodeSourceMember(
                    source_type="CHAT_MESSAGE", source_id=str(identifier),
                    source_digest=evidence.source_digest, role=role, text=text,
                    total_characters=len(text),
                    actor_label=labels.get(evidence.actor_world_character_id),
                    occurred_at=(evidence.source_created_at.replace(tzinfo=UTC) if evidence.source_created_at.tzinfo is None else evidence.source_created_at).isoformat(),
                ))
            if len(members) != 2:
                rejected.append(turn.request_id)
                continue
            revision = sha256(json.dumps({
                "request": turn.request_id,
                "sources": [(m.source_id, m.source_digest) for m in members],
                "thought": asdict(turn.thought), "thought_recorded": turn.thought_recorded,
            }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            units.append(EpisodeSourceUnit(
                unit_key=f"chat:{turn.request_id}", unit_revision=revision,
                scope=scope, kind="chat_turn", occurred_at=turn.occurred_at,
                members=tuple(members), thread_id=thread_id, thought=turn.thought,
                thought_reference=f"chat:{turn.assistant_message_id}" if turn.thought_recorded else None,
            ))
        return tuple(units)

    context_units, new_units = convert(context), convert(fresh)
    return EpisodeChatPage(
        new_units=new_units, context_units=context_units,
        through_sequence=fresh[-1].assistant_message_id if fresh else after,
        rejected_request_ids=tuple(dict.fromkeys(rejected)),
    )
