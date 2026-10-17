"""Situation-only hybrid validation followed by bounded original/thought reads."""

from datetime import UTC, datetime
from dataclasses import replace
from hashlib import sha256
import json
from contextlib import nullcontext

from sqlalchemy import select
from app.contracts.search_diagnostics import lineage

from app.domains.memory.contracts.hybrid_recall import (
    EpisodeValidationSnapshot, HybridCanonicalResult, HybridHydrationResult, HybridSourceReceipt, RecallAxisStatus,
    RecallCurrentnessError,
)
from app.domains.memory.contracts.recall import CanonicalRecallRecord, RecallDocumentKind, SOURCE_KIND_BY_TYPE
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view, episode_provider_reference
from app.domains.memory.repository.episode_candidates import SqlAlchemyEpisodeCandidates
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.recall_records import _item_retrievable, _item_scope
from app.domains.memory.repository.situation_reads import representation
from app.domains.memory.contracts.access_validation import MemoryAccessValidation
from app.domains.memory.policies.hybrid_selection import select_records, selection_steps


def _aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SqlAlchemyEpisodeHybridReader:
    def __init__(self, session_factory, *, detail_reader_factory, clock=None, access_observer=None, phase=None):
        self.factory, self.details = session_factory, detail_reader_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.access_observer = access_observer
        self.phase = phase or (lambda _: nullcontext())

    def _observe(self, validation):
        if self.access_observer is not None:
            self.access_observer(validation.metrics())

    def resolve(self, request, candidates):
        now = self.clock()
        with self.factory() as db:
            validation = MemoryAccessValidation(db, now)
            with self.phase("revalidate"):
                records = self._revalidate(db, request, candidates, now, validation)
            with self.phase("hydrate"):
                hydration = self._hydrate(db, request, select_records(request, records), now, validation)
            self._observe(validation)
            return HybridCanonicalResult(len(records), hydration, selection_steps(request, records))

    def revalidate(self, request, candidates):
        now = self.clock()
        with self.factory() as db:
            validation = MemoryAccessValidation(db, now)
            result = self._revalidate(db, request, candidates, now, validation)
            self._observe(validation)
            return result

    def assert_current(self, result, delivered_ids):
        """A fresh bounded read, independent of the earlier resolve's memo/time."""
        if not delivered_ids:
            return
        snapshot = result.validation_snapshot
        originals = {row.memory_item_id: row for row in result.records}
        if (snapshot is None or snapshot.scope != result.scope
                or not set(delivered_ids) <= originals.keys()):
            raise RecallCurrentnessError("memory_delivery_binding_changed")
        now = self.clock()
        with self.factory() as db:
            validation = MemoryAccessValidation(db, now)
            rows = {row.id: row for row in db.scalars(select(MemoryItem).where(
                MemoryItem.id.in_(snapshot.seed_memory_ids)))}
            seeds = tuple(CanonicalRecallRecord(f"memory-item:{identifier}", RecallDocumentKind.MEMORY_ITEM,
                identifier, rows[identifier].summary, _aware(rows[identifier].valid_from),
                memory_item_id=identifier, metadata={"item_version": str(rows[identifier].version)})
                for identifier in snapshot.seed_memory_ids if identifier in rows)
            # Retain the original traversal and packet budgets. Removing unseen
            # packets before budgeting would change the delivered excerpts.
            fresh = self._hydrate(db, result, seeds, now, validation)
            self._observe(validation)
            if replace(fresh.validation_snapshot, captured_at=snapshot.captured_at) != snapshot:
                raise RecallCurrentnessError("memory_delivery_followup_changed")
            current = {row.memory_item_id: row for row in fresh.records}
            if any(current.get(identifier) != originals[identifier] for identifier in delivered_ids):
                raise RecallCurrentnessError("memory_delivery_source_changed")

    def _revalidate(self, db, request, candidates, now, validation):
        if len(candidates) > 50:
            raise ValueError("hybrid_candidate_limit")
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
            from app.domains.memory.models.activity_situation import MemoryActivitySituationSource
            for source in db.scalars(select(MemoryActivitySituationSource).where(
                MemoryActivitySituationSource.memory_item_id.in_(rows))):
                if source.source.get("source_type") in types:
                    matching.add(source.memory_item_id)
        from app.domains.memory.repository.access_batch import prepare_access, prepare_representation
        eligible = tuple(item for item in rows.values() if _item_retrievable(item, now) and any(
            ranked.candidate.memory_item_id == item.id
            and ranked.candidate.kind is RecallDocumentKind.MEMORY_ITEM
            and RecallDocumentKind.MEMORY_ITEM in request.kinds
            and ranked.candidate.document_id == f"memory-item:{item.id}"
            and ranked.candidate.canonical_source_id == item.id
            and ranked.version == item.version
            and ranked.content_hash == sha256(item.summary.encode()).hexdigest()
            for ranked in candidates) and (request.thread_id is None or item.thread_id == request.thread_id)
            and (matching is None or item.id in matching)
            and (request.counterpart_world_character_id is None
                 or item.counterpart_world_character_id == request.counterpart_world_character_id
                 or any(request.counterpart_world_character_id in {e.actor_world_character_id, e.target_world_character_id}
                        for e in evidence_by_item.get(item.id, ()))))
        prepare_representation(validation, eligible)
        representations = {}
        for item in eligible:
            try:
                kind = representation(db, item, validation=validation)
            except ValueError:
                continue
            occurred = _aware(item.valid_from)
            material = evidence_by_item.get(item.id, ())
            times = [occurred] if kind == "activity_situation_v1" else [_aware(e.source_created_at) for e in material] or [occurred]
            if (request.occurred_from is not None and max(times) < request.occurred_from
                or request.occurred_to is not None and min(times) >= request.occurred_to):
                continue
            representations[item.id] = kind
        prepare_access(db, tuple(item for item in eligible if item.id in representations), now,
            reader=self.details(db), validation=validation)
        result, seen = [], set()
        from app.domains.memory.repository.episode_privacy import currently_accessible
        privacy_reader = self.details(db)
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
            if item.id not in representations:
                continue
            item_representation = representations[item.id]
            if not currently_accessible(db, privacy_reader, request.scope, item, now, validation=validation):
                continue
            seen.add(item.id)
            result.append(CanonicalRecallRecord(f"memory-item:{item.id}", RecallDocumentKind.MEMORY_ITEM,
                item.id, item.summary, occurred, memory_item_id=item.id,
                counterpart_world_character_id=item.counterpart_world_character_id, thread_id=item.thread_id,
                metadata={"item_version": str(item.version), "memory_kind": item.memory_kind,
                          "representation": item_representation}))
        return tuple(result)

    def axis_request(self, request):
        # Existing projections have one timestamp/counterpart per document.
        # Do not mis-filter a multi-source episode through its first source;
        # enforce the complete bounded candidate manifest after RRF instead.
        return replace(request, occurred_from=None, occurred_to=None, counterpart_world_character_id=None)

    def hydrate(self, request, records):
        now = self.clock()
        with self.factory() as db:
            validation = MemoryAccessValidation(db, now)
            result = self._hydrate(db, request, records, now, validation)
            self._observe(validation)
            return result

    def _hydrate(self, db, request, records, now, validation):
        if len(records) > 50:
            raise ValueError("hybrid_candidate_limit")
        # The selection/hydration boundary must not quietly accept a
        # different situation version than the one that survived RRF.
        snapshots = {row.id: row for row in db.scalars(select(MemoryItem).where(
            MemoryItem.id.in_([r.memory_item_id for r in records if r.memory_item_id])))}
        ids = tuple(row.memory_item_id for row in records if row.memory_item_id in snapshots
            and str(snapshots[row.memory_item_id].version) == row.metadata.get("item_version")
            and snapshots[row.memory_item_id].summary == row.text)
        candidate_reader = SqlAlchemyEpisodeCandidates(db, source_reader=self.details(db))
        updates = candidate_reader.collect_followups(scope=request.scope, seed_ids=ids, now=now)
        packets = SqlAlchemyEpisodePackets(db, detail_reader=self.details(db)).read(
            scope=request.scope, item_ids=updates.item_ids, now=now, validation=validation)
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
            # Only source refs actually retained after packet budgeting.
            retained = {source.get("reference", source.get("ref")) for unit in value["units"] for source in unit["sources"]}
            times = [_aware(source.occurred_at) for unit in packet.units for source in unit.sources
                if source.status == "verified" and source.occurred_at is not None
                and episode_provider_reference("source", source.reference) in retained]
            metadata.update(event_time_from=min(times).isoformat() if times else "",
                event_time_to=max(times).isoformat() if times else "", recorded_at=_aware(item.created_at).isoformat())
            metadata["source_authors"] = json.dumps([
                [episode_provider_reference("source", source.reference), source.author_id]
                for unit in packet.units for source in unit.sources
                if source.status == "verified" and source.author_id and
                episode_provider_reference("source", source.reference) in retained], separators=(",", ":"))
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
