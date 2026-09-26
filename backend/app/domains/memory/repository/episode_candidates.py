"""Bounded SQL candidates and follow-up edges; no generation or embedding calls."""

from dataclasses import dataclass
from datetime import UTC
from hashlib import sha256

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from app.domains.memory.contracts.episode import EpisodePriorCandidate, MAX_PRIOR_EPISODES
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.repository.recall_records import _item_retrievable


@dataclass(frozen=True, slots=True)
class EpisodeFollowups:
    item_ids: tuple[str, ...]
    truncated: bool
    link_probes: tuple[tuple[str, str, str], ...] = ()
    item_revisions: tuple[tuple[str, int, str], ...] = ()


def _owned(item, scope):
    return and_(item.owner_id == scope.owner_id, item.world_id == scope.world_id,
                item.subject_world_character_id == scope.subject_world_character_id)


def _available(item, now):
    return and_(item.status == "active", item.deleted_at.is_(None), item.valid_from <= now,
                or_(item.valid_until.is_(None), item.valid_until > now))


class SqlAlchemyEpisodeCandidates:
    def __init__(self, session):
        self.session = session

    def _enabled(self, scope):
        return self.session.scalar(select(MemoryScopeSettingModel.id).where(
            _owned(MemoryScopeSettingModel, scope), MemoryScopeSettingModel.enabled.is_(True))) is not None

    def priors(self, *, scope, now, thread_id=None, source_identities=(), ranked_fts_ids=()):
        """Exact source links, then scoped FTS hits, then bounded recent items.

        Runtime supplies already bounded lexical hits if available. They are
        untrusted IDs, never permission grants. Public SNS never reads private
        chat episodes through this candidate path. A Chat bundle only sees its
        own thread plus public experiences.
        """
        identities = tuple(dict.fromkeys(source_identities))
        ranked = tuple(dict.fromkeys(ranked_fts_ids))
        if len(identities) > 100 or len(ranked) > 50:
            raise ValueError("episode_prior_candidate_limit")
        if not self._enabled(scope):
            return ()
        audience = MemoryItem.thread_id.is_(None)
        if thread_id is not None:
            audience = or_(audience, MemoryItem.thread_id == thread_id)
        base = select(MemoryItem).where(_owned(MemoryItem, scope), _available(MemoryItem, now), audience)
        result = {}

        def add(rows):
            for row in rows:
                if len(result) >= MAX_PRIOR_EPISODES:
                    break
                if _item_retrievable(row, now) and len(row.summary) <= 2000:
                    result.setdefault(row.id, EpisodePriorCandidate(row.id, row.version, row.summary))

        if identities:
            linked = exists(select(MemoryItemEvidence.id).where(
                MemoryItemEvidence.memory_item_id == MemoryItem.id,
                or_(*(and_(MemoryItemEvidence.source_type == kind,
                           MemoryItemEvidence.source_id == identifier) for kind, identifier in identities))))
            add(self.session.scalars(base.where(linked).order_by(MemoryItem.created_at.desc(), MemoryItem.id).limit(8)))
        if len(result) < 8 and ranked:
            rows = {row.id: row for row in self.session.scalars(base.where(MemoryItem.id.in_(ranked)))}
            add(rows[identifier] for identifier in ranked if identifier in rows)
        if len(result) < 8:
            add(self.session.scalars(base.order_by(MemoryItem.created_at.desc(), MemoryItem.id).limit(8)))
        return tuple(result.values())

    def followups(self, *, scope, item_ids, now, limit=12, depth_limit=8):
        """Follow only owned, active edges; explicitly report bounded traversal.

        Keep original RRF order and append updates without overwriting the
        historical situation. Even corrupt cycles cannot loop or cross scope.
        The caller must expose `truncated` when it cannot inspect all updates.
        """
        roots = tuple(dict.fromkeys(item_ids))
        if len(roots) > 50 or not 1 <= limit <= 50 or not 1 <= depth_limit <= 8:
            raise ValueError("episode_followup_limit")
        if not roots or not self._enabled(scope):
            return EpisodeFollowups((), False)
        available = set(self.session.scalars(select(MemoryItem.id).where(
            MemoryItem.id.in_(roots), _owned(MemoryItem, scope), _available(MemoryItem, now))))
        ordered = [identity for identity in roots if identity in available]
        truncated = len(ordered) > limit
        ordered = ordered[:limit]
        visited, frontier = set(ordered), tuple(ordered)
        inspected = set(roots)
        probes = []
        prior = aliased(MemoryItem)
        for _ in range(depth_limit):
            if not frontier:
                break
            rows = self.session.execute(select(MemoryEpisodeLink.prior_item_id, MemoryItem.id,
                MemoryEpisodeLink.created_at).join(
                MemoryItem, MemoryItem.id == MemoryEpisodeLink.following_item_id,
            ).join(prior, prior.id == MemoryEpisodeLink.prior_item_id).where(
                MemoryEpisodeLink.prior_item_id.in_(frontier), _owned(prior, scope), _owned(MemoryItem, scope),
                _available(prior, now), _available(MemoryItem, now),
                # A malformed edge cannot move a public episode into a private thread.
                or_(MemoryItem.thread_id.is_(None), MemoryItem.thread_id == prior.thread_id),
            ).order_by(MemoryEpisodeLink.created_at.desc(), MemoryItem.id,
                MemoryEpisodeLink.prior_item_id).limit(65)).all()
            if len(rows) > 64:
                truncated = True
            next_ids = []
            for prior_id, identifier, created_at in rows[:64]:
                inspected.add(identifier)
                stamp = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at.astimezone(UTC)
                probes.append((prior_id, identifier, stamp.isoformat()))
                if identifier in visited:
                    continue
                visited.add(identifier)
                if len(ordered) == limit:
                    truncated = True
                    continue
                ordered.append(identifier)
                next_ids.append(identifier)
            frontier = tuple(next_ids)
        else:
            # Conservatively mark depth-bound results, without claiming that
            # the last visited update was necessarily the latest one.
            truncated = truncated or bool(frontier)
        revisions = tuple(sorted((row.id, row.version, sha256(row.summary.encode()).hexdigest())
            for row in self.session.scalars(select(MemoryItem).where(
                MemoryItem.id.in_(inspected), _owned(MemoryItem, scope), _available(MemoryItem, now)))))
        return EpisodeFollowups(tuple(ordered), truncated, tuple(probes), revisions)

    def collect_followups(self, *, scope, seed_ids, now, limit=12, depth_limit=8):
        """Apply one shared budget in original seed order for hydrate and guard."""
        seeds = tuple(dict.fromkeys(seed_ids))
        if len(seeds) > 50 or not 1 <= limit <= 50 or not 1 <= depth_limit <= 8:
            raise ValueError("episode_followup_limit")
        ordered, probes, revisions = [], [], {}
        truncated = False
        for identifier in seeds:
            if identifier in ordered:
                continue
            if len(ordered) >= limit:
                truncated = True
                break
            linked = self.followups(scope=scope, item_ids=(identifier,), now=now,
                limit=limit - len(ordered), depth_limit=depth_limit)
            ordered.extend(value for value in linked.item_ids if value not in ordered)
            probes.extend(linked.link_probes)
            revisions.update((item_id, (version, digest))
                for item_id, version, digest in linked.item_revisions)
            truncated |= linked.truncated
        return EpisodeFollowups(tuple(ordered), truncated, tuple(probes),
            tuple(sorted((item_id, version, digest) for item_id, (version, digest) in revisions.items())))
