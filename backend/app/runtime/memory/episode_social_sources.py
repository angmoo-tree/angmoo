"""Build observed SNS branches; never turn unseen neighboring replies into experience."""

from dataclasses import asdict, dataclass
from datetime import UTC
from hashlib import sha256
import json

from sqlalchemy import or_, select

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.episode import EpisodeSourceMember, EpisodeSourceUnit
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.social.models.activity_thought import SocialActivityThought
from app.domains.social.models.posts import Post
from app.domains.relationships.models.social import SocialEventEvidence
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader, _rows
from app.runtime.memory.episode_labels import episode_actor_labels


@dataclass(frozen=True, slots=True)
class SocialEpisodeInput:
    group_key: str
    identity: tuple[str, str]
    unit: EpisodeSourceUnit


@dataclass(frozen=True, slots=True)
class SocialEpisodeSources:
    inputs: tuple[SocialEpisodeInput, ...]
    rejected: tuple[tuple[tuple[str, str], str], ...]


def build_episode_social_sources(session, *, scope, identities):
    identities = tuple(dict.fromkeys(identities))
    if len(identities) > 100 or any(kind in {"CHAT_MESSAGE", "OWNER_MEMORY_REQUEST"} for kind, _ in identities):
        raise ValueError("episode_social_page_invalid")
    reader = RuntimeEpisodeDetailReader(session)
    details = reader.read_sources(scope=scope, identities=identities)
    posts = {p.id: p for p in _rows(session, Post, Post.id,
        (identifier for kind, identifier in identities if kind in {"POST", "REPLY"}))}
    frontier = {p.reply_to_post_id for p in posts.values() if p.reply_to_post_id}
    for _ in range(8):
        if not frontier:
            break
        found = _rows(session, Post, Post.id, frontier)
        posts.update({p.id: p for p in found})
        frontier = {p.reply_to_post_id for p in found if p.reply_to_post_id and p.reply_to_post_id not in posts}
    ancestor_identities = tuple(("REPLY" if p.reply_to_post_id else "POST", p.id) for p in posts.values()
                                if ("REPLY" if p.reply_to_post_id else "POST", p.id) not in details)
    details.update(reader.read_sources(scope=scope, identities=ancestor_identities))
    event_ids = {d.evidence.source_event_id for d in details.values() if d.evidence.source_event_id}
    reaction_events = {}
    reaction_ids = [identifier for kind, identifier in identities if kind == "REACTION"]
    if reaction_ids:
        receipts = session.scalars(select(SocialEventEvidence).where(
            SocialEventEvidence.source_object_type == "post_like",
            SocialEventEvidence.source_object_id.in_(reaction_ids))).all()
        for receipt in receipts:
            reaction_events.setdefault(receipt.source_object_id, set()).add(receipt.social_event_id)
            event_ids.add(receipt.social_event_id)
    labels = episode_actor_labels(session, scope=scope, actor_ids=(d.evidence.actor_world_character_id for d in details.values()))
    thoughts = session.scalars(select(SocialActivityThought).where(
        SocialActivityThought.owner_id == scope.owner_id, SocialActivityThought.world_id == scope.world_id,
        SocialActivityThought.actor_world_character_id == scope.subject_world_character_id,
        or_(SocialActivityThought.source_post_id.in_(posts), SocialActivityThought.social_event_id.in_(event_ids)),
    ).order_by(SocialActivityThought.created_at.desc(), SocialActivityThought.id)).all()
    valid_thoughts = reader.read_thoughts(scope=scope, references=tuple(f"social:{t.id}" for t in thoughts))
    inputs, rejected = [], []

    def allowed(identity):
        material = details.get(identity)
        return memory_evidence_blocked_code(scope=scope, source_type=MemorySourceTypeV1(identity[0]),
            source_id=identity[1], evidence=None if material is None else material.evidence)

    for identity in identities:
        blocked = allowed(identity)
        if blocked:
            rejected.append((identity, blocked))
            continue
        material = details[identity]
        source = material.evidence
        selected = [identity]
        seen = {identity[1]}
        root = identity[1]
        parent = posts.get(identity[1]).reply_to_post_id if identity[0] in {"POST", "REPLY"} else None
        partial = False
        for _ in range(8):
            if parent is None:
                break
            post = posts.get(parent)
            if post is None or parent in seen:
                partial = True
                break
            seen.add(parent)
            key = ("REPLY" if post.reply_to_post_id else "POST", parent)
            if allowed(key):
                partial = True
                break
            selected.append(key)
            root, parent = parent, post.reply_to_post_id
        else:
            partial = parent is not None
        thought, thought_reference = ActivityThought(), None
        if source.actor_world_character_id == scope.subject_world_character_id:
            for row in thoughts:
                if ((identity[0] in {"POST", "REPLY"} and row.source_post_id == identity[1])
                    or (source.source_event_id is not None and row.social_event_id == source.source_event_id)
                    or (identity[0] == "REACTION" and row.social_event_id in reaction_events.get(identity[1], set()))):
                    ref = f"social:{row.id}"
                    if ref in valid_thoughts:
                        thought, thought_reference = valid_thoughts[ref], ref
                        break
        members = tuple(EpisodeSourceMember(kind, identifier, details[(kind, identifier)].evidence.source_digest,
            "self" if details[(kind, identifier)].evidence.actor_world_character_id == scope.subject_world_character_id else "observed_counterpart",
            details[(kind, identifier)].text, total_characters=len(details[(kind, identifier)].text),
            actor_label=labels.get(details[(kind, identifier)].evidence.actor_world_character_id),
            occurred_at=(details[(kind, identifier)].evidence.source_created_at.replace(tzinfo=UTC)
                if details[(kind, identifier)].evidence.source_created_at.tzinfo is None
                else details[(kind, identifier)].evidence.source_created_at).isoformat())
            for kind, identifier in reversed(selected))
        legacy = source.subjective_context if thought_reference is None else None
        revision = sha256(json.dumps({
            "members": [(m.source_type, m.source_id, m.source_digest) for m in members],
            "thought": asdict(thought), "thought_ref": thought_reference,
            "legacy": legacy, "partial": partial,
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        occurred = source.source_created_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        unit = EpisodeSourceUnit(f"social:{identity[0]}:{identity[1]}", revision, scope,
            "sns_interaction" if identity[0] in {"POST", "REPLY"} else "event", occurred, members,
            thought=thought, thought_reference=thought_reference,
            coverage="partial_source" if partial else "complete", legacy_subjective_context=legacy)
        inputs.append(SocialEpisodeInput(f"post:{root}" if identity[0] in {"POST", "REPLY"} else "events", identity, unit))
    return SocialEpisodeSources(tuple(inputs), tuple(rejected))
