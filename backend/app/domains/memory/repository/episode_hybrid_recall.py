"""Situation-only hybrid validation followed by bounded original/thought reads."""

from datetime import UTC, datetime
from dataclasses import replace
from hashlib import sha256
import json

from sqlalchemy import select
from app.contracts.search_diagnostics import lineage

from app.domains.memory.contracts.hybrid_recall import (
    EpisodeValidationSnapshot, HybridHydrationResult, HybridSourceReceipt, RecallAxisStatus,
)
from app.domains.memory.contracts.recall import CanonicalRecallRecord, RecallDocumentKind, SOURCE_KIND_BY_TYPE
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view, episode_provider_reference
from app.domains.memory.repository.episode_candidates import SqlAlchemyEpisodeCandidates
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.recall_records import _item_retrievable, _item_scope


def _aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SqlAlchemyEpisodeHybridReader:
    def __init__(self, session_factory, *, detail_reader_factory, clock=None):
        self.factory, self.details = session_factory, detail_reader_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def revalidate(self, request, candidates):
        if len(candidates) > 50:
            raise ValueError("hybrid_candidate_limit")
        now = self.clock()
        with self.factory() as db:
            setting = db.scalar(select(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.owner_id == request.scope.owner_id,
                MemoryScopeSettingModel.world_id == request.scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id == request.scope.subject_world_character_id))
            if setting is None or not setting.enabled:
                return ()
            rows = {row.id: row for row in db.scalars(select(MemoryItem).where(
                MemoryItem.id.in_([row.candidate.memory_item_id for row in candidates]),
                MemoryItem.owner_id == request.scope.owner_id, MemoryItem.world_id == request.scope.world_id,
                MemoryItem.subject_world_character_id == request.scope.subject_world_character_id))}
            matching = None
            evidence_by_item = {}
            for evidence in db.scalars(select(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id.in_(rows))):
                evidence_by_item.setdefault(evidence.memory_item_id, []).append(evidence)
            if request.episode_source_kinds:
                types = [kind.value for kind, family in SOURCE_KIND_BY_TYPE.items() if family in request.episode_source_kinds]
                matching = set(db.scalars(select(MemoryItemEvidence.memory_item_id).where(
                    MemoryItemEvidence.memory_item_id.in_(rows), MemoryItemEvidence.source_type.in_(types))))
            result, seen = [], set()
            for ranked in candidates:
                candidate = ranked.candidate
                item = rows.get(candidate.memory_item_id)
                if (item is None or not _item_retrievable(item, now) or _item_scope(item) != request.scope
                    or candidate.kind is not RecallDocumentKind.MEMORY_ITEM
                    or RecallDocumentKind.MEMORY_ITEM not in request.kinds
                    or candidate.document_id != f"memory-item:{item.id}" or candidate.canonical_source_id != item.id
                    or ranked.version != item.version or ranked.content_hash != sha256(item.summary.encode()).hexdigest()
                    or item.id in seen or (matching is not None and item.id not in matching)):
                    continue
                if request.thread_id is not None and item.thread_id != request.thread_id:
                    continue
                material = evidence_by_item.get(item.id, ())
                if request.counterpart_world_character_id is not None and not (
                    item.counterpart_world_character_id == request.counterpart_world_character_id or any(
                        request.counterpart_world_character_id in {e.actor_world_character_id, e.target_world_character_id}
                        for e in material)):
                    continue
                # Episode time is its canonical experience time, never the time
                # a later raw source happened to be hydrated for this request.
                occurred = _aware(item.valid_from)
                times = [_aware(e.source_created_at) for e in material] or [occurred]
                # These are observed/source times, not dates mentioned in text.
                # A multi-day episode overlaps a query if its material interval does.
                if (request.occurred_from is not None and max(times) < request.occurred_from
                    or request.occurred_to is not None and min(times) >= request.occurred_to):
                    continue
                seen.add(item.id)
                result.append(CanonicalRecallRecord(f"memory-item:{item.id}", RecallDocumentKind.MEMORY_ITEM,
                    item.id, item.summary, occurred, memory_item_id=item.id,
                    counterpart_world_character_id=item.counterpart_world_character_id, thread_id=item.thread_id,
                    metadata={"item_version": str(item.version), "memory_kind": item.memory_kind,
                              "representation": "episode_v1"}))
            return tuple(result)

    def axis_request(self, request):
        # Existing projections have one timestamp/counterpart per document.
        # Do not mis-filter a multi-source episode through its first source;
        # enforce the complete bounded candidate manifest after RRF instead.
        return replace(request, occurred_from=None, occurred_to=None, counterpart_world_character_id=None)

    def hydrate(self, request, records):
        if len(records) > 50:
            raise ValueError("hybrid_candidate_limit")
        now = self.clock()
        with self.factory() as db:
            # The selection/hydration boundary must not quietly accept a
            # different situation version than the one that survived RRF.
            snapshots = {row.id: row for row in db.scalars(select(MemoryItem).where(
                MemoryItem.id.in_([r.memory_item_id for r in records if r.memory_item_id])))}
            ids = tuple(row.memory_item_id for row in records if row.memory_item_id in snapshots
                and str(snapshots[row.memory_item_id].version) == row.metadata.get("item_version")
                and snapshots[row.memory_item_id].summary == row.text)
            candidate_reader = SqlAlchemyEpisodeCandidates(db)
            updates = candidate_reader.collect_followups(scope=request.scope, seed_ids=ids, now=now)
            packets = SqlAlchemyEpisodePackets(db, detail_reader=self.details(db)).read(
                scope=request.scope, item_ids=updates.item_ids, now=now)
            packets = tuple(replace(packet, followup_truncated=updates.truncated) for packet in packets)
            delivery = bounded_episode_packets(episode_provider_view(packets))
            lineage("hydrate", "count", count=len(packets))
            lineage("limit", "excluded", count=delivery.omitted_units, reason="character_budget")
            by_ref = {episode_provider_reference("episode", packet.reference): packet for packet in packets}
            items = {row.id: row for row in db.scalars(select(MemoryItem).where(MemoryItem.id.in_(updates.item_ids)))}
            output, receipts = [], []
            for value in delivery.packets:
                packet = by_ref[value["ref"]]
                item = items[packet.reference]
                lineage("hydrate", "linked", identities={"memory_ref": ("m", item.id)}, count=len(value["units"]),
                        reason="degraded" if value["partial"] else "available")
                for unit in packet.units:
                    for source in unit.sources:
                        lineage("hydrate", "accepted" if source.status == "verified" else "excluded",
                            identities={"memory_ref": ("m", item.id), "source_ref": ("s", source.reference)},
                            reason="available" if source.status == "verified" else "missing" if source.status == "missing" else "validation")
                # Preserve the original ranked identity for the final request
                # receipt. Follow-ups are explicit linked context, not new hits.
                metadata = {"item_version": str(item.version), "memory_kind": item.memory_kind,
                    "episode_packet": "v1", "partial": str(value["partial"]).lower(),
                    "followup_truncated": str(updates.truncated).lower()}
                output.append(CanonicalRecallRecord(f"memory-item:{item.id}", RecallDocumentKind.MEMORY_ITEM,
                    item.id, json.dumps(value, ensure_ascii=False, separators=(",", ":")), _aware(item.valid_from),
                    memory_item_id=item.id, counterpart_world_character_id=item.counterpart_world_character_id,
                    thread_id=item.thread_id, metadata=metadata))
                receipts.append(HybridSourceReceipt(f"memory-item:{item.id}",
                    RecallAxisStatus.PARTIAL if value["partial"] or updates.truncated else RecallAxisStatus.READY,
                    value["source_statuses"]["verified"]))
            snapshot = EpisodeValidationSnapshot(
                scope=request.scope, seed_memory_ids=ids,
                hydrated_memory_ids=updates.item_ids,
                item_revisions=updates.item_revisions, link_probes=updates.link_probes,
                traversal_truncated=updates.truncated, captured_at=now)
            return HybridHydrationResult(tuple(output), tuple(receipts), snapshot)
