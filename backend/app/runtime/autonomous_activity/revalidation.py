"""Read-only final input validation, without a second embedding/search call."""
import json
from datetime import UTC, datetime
from sqlalchemy import select
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.episode_candidates import SqlAlchemyEpisodeCandidates
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader


def assert_memories_current(db, *, owner_id, world_id, actor_id, memories):
    scope = MemoryScope(owner_id, world_id, actor_id)
    now = datetime.now(UTC)
    for result in memories.values():
        ids = tuple(result.get("ranked_memory_ids", ()))
        if not ids or not result.get("packets"):
            continue
        linked = SqlAlchemyEpisodeCandidates(db).followups(scope=scope, item_ids=ids, now=now, limit=12)
        # Hydration already bounded the follow-up graph. Re-running traversal
        # with hydrated rows as roots can discover pre-existing omitted rows;
        # that is not a concurrent correction. New links/items still invalidate.
        if not set(ids) <= set(linked.item_ids):
            raise ValueError("activity_memory_followup_changed")
        extra = set(linked.item_ids) - set(ids)
        if extra:
            threshold = result.get("retrieved_after")
            if not threshold or not any(p.get("followup_truncated") for p in result["packets"]):
                raise ValueError("activity_memory_followup_changed")
            threshold = datetime.fromisoformat(threshold).astimezone(UTC).replace(tzinfo=None)
            new_item = db.scalar(select(MemoryItem.id).where(MemoryItem.id.in_(extra), MemoryItem.created_at > threshold).limit(1))
            new_link = db.scalar(select(MemoryEpisodeLink.following_item_id).where(
                MemoryEpisodeLink.prior_item_id.in_(linked.item_ids),
                MemoryEpisodeLink.following_item_id.in_(linked.item_ids),
                MemoryEpisodeLink.created_at > threshold).limit(1))
            if new_item or new_link:
                raise ValueError("activity_memory_followup_changed")
        packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(scope=scope, item_ids=ids, now=now)
        refreshed = bounded_episode_packets(episode_provider_view(packets)).packets
        by_ref = {p["ref"]: p for p in refreshed}
        for old in result["packets"]:
            fresh = by_ref.get(old.get("ref"))
            if fresh is None or old.get("situation") != fresh.get("situation"):
                raise ValueError("activity_memory_changed")
            # Compare exactly the units supplied, allowing additional omitted units.
            current_units = {u["ref"]: u for u in fresh.get("units", [])}
            if any(current_units.get(u["ref"]) != u for u in old.get("units", [])):
                raise ValueError("activity_memory_source_changed")
