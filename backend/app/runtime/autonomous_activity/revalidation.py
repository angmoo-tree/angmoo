"""Read-only final input validation, without a second embedding/search call."""
from dataclasses import asdict
import json
from datetime import UTC, datetime
from sqlalchemy import select
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.episode_candidates import SqlAlchemyEpisodeCandidates
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.domains.memory.policies.episode_provider_view import episode_provider_reference
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader


def _rows(value):
    if not isinstance(value, list) or any(not isinstance(row, list) or len(row) != 3 for row in value):
        raise ValueError("activity_memory_validation_unavailable")
    return tuple(tuple(row) for row in value)


def _assert_snapshot_current(db, *, scope, result, snapshot, now):
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1
            or snapshot.get("policy_version") != "episode-followups-v1"
            or snapshot.get("scope") != asdict(scope)
            or snapshot.get("traversal_limit") != 12 or snapshot.get("depth_limit") != 8
            or not isinstance(snapshot.get("seed_memory_ids"), list)
            or not isinstance(snapshot.get("hydrated_memory_ids"), list)
            or not isinstance(snapshot.get("traversal_truncated"), bool)
            or len(snapshot["seed_memory_ids"]) > 50
            or len(snapshot["hydrated_memory_ids"]) > 12
            or any(not isinstance(value, str) or not value for value in
                   (*snapshot["seed_memory_ids"], *snapshot["hydrated_memory_ids"]))):
        raise ValueError("activity_memory_validation_unavailable")
    updates = SqlAlchemyEpisodeCandidates(db).collect_followups(scope=scope,
        seed_ids=tuple(snapshot["seed_memory_ids"]), now=now,
        limit=snapshot["traversal_limit"], depth_limit=snapshot["depth_limit"])
    if (updates.item_ids != tuple(snapshot["hydrated_memory_ids"])
            or updates.link_probes != _rows(snapshot.get("link_probes", ()))
            or updates.truncated != snapshot.get("traversal_truncated")):
        raise ValueError("activity_memory_followup_changed")
    if updates.item_revisions != _rows(snapshot.get("item_revisions", ())):
        raise ValueError("activity_memory_changed")
    ids = tuple(result.get("ranked_memory_ids", ()))
    if any(identifier not in updates.item_ids for identifier in ids):
        raise ValueError("activity_memory_validation_unavailable")
    if not result.get("packets"):
        return
    packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(
        scope=scope, item_ids=ids, now=now)
    fresh_by_ref = {packet.reference: packet for packet in episode_provider_view(packets)}
    for old in result["packets"]:
        fresh = fresh_by_ref.get(old.get("ref"))
        if (fresh is None or old.get("situation") != fresh.summary
                or old.get("representation") != fresh.representation
                or old.get("follows") != list(fresh.follows_references)):
            raise ValueError("activity_memory_changed")
        fresh_units = {unit.reference: unit for unit in fresh.units}
        if len(old.get("units", [])) + old.get("omitted_units", 0) != len(fresh_units):
            raise ValueError("activity_memory_source_changed")
        statuses = {status: sum(source.status == status for unit in fresh.units for source in unit.sources)
            for status in ("verified", "missing", "changed", "unavailable")}
        if old.get("source_statuses") != statuses:
            raise ValueError("activity_memory_source_changed")
        for old_unit in old.get("units", []):
            current = fresh_units.get(old_unit.get("ref"))
            if (current is None or old_unit.get("coverage") != current.coverage
                    or old_unit.get("thought_ref") != current.thought_reference
                    or old_unit.get("legacy_action_declaration") != current.legacy_subjective_context):
                raise ValueError("activity_memory_source_changed")
            previous_thought = old_unit.get("thought")
            if previous_thought != {"already_in_context": True} and previous_thought != asdict(current.thought):
                raise ValueError("activity_memory_source_changed")
            current_sources = {source.reference: source for source in current.sources}
            if len(old_unit.get("sources", [])) != len(current.sources):
                raise ValueError("activity_memory_source_changed")
            for previous_source in old_unit.get("sources", []):
                source = current_sources.get(previous_source.get("reference", previous_source.get("ref")))
                if source is None:
                    raise ValueError("activity_memory_source_changed")
                if previous_source.get("already_in_context"):
                    if source.status != "verified" or any(previous_source.get(k) != getattr(source, k)
                        for k in ("start_offset", "end_offset")):
                        raise ValueError("activity_memory_source_changed")
                elif previous_source != asdict(source):
                    raise ValueError("activity_memory_source_changed")


def assert_memories_current(db, *, owner_id, world_id, actor_id, memories, validations=None):
    scope = MemoryScope(owner_id, world_id, actor_id)
    now = datetime.now(UTC)
    for target, result in memories.items():
        snapshot = (validations or {}).get(target)
        if snapshot is not None:
            _assert_snapshot_current(db, scope=scope, result=result, snapshot=snapshot, now=now)
            continue
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
