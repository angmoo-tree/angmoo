"""Bulk manifest loading; missing original material does not erase a situation."""

from dataclasses import asdict
from hashlib import sha256
import json

from sqlalchemy import select

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketSource, EpisodePacketUnit
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeInfo, MemoryEpisodeUnit, MemoryEpisodeUnitEvidence, MemoryEpisodeLink
from app.domains.memory.repository.recall_records import _item_retrievable
from app.domains.memory.service.items import memory_evidence_blocked_code


class SqlAlchemyEpisodePackets:
    def __init__(self, session, *, detail_reader):
        self.session, self.reader = session, detail_reader

    def read(self, *, scope, item_ids, now, require_enabled=True):
        ids = tuple(dict.fromkeys(item_ids))
        if len(ids) > 50:
            raise ValueError("episode_packet_candidate_limit")
        if not ids:
            return ()
        rows = self.session.scalars(select(MemoryItem).join(
            MemoryScopeSettingModel,
            (MemoryScopeSettingModel.owner_id == MemoryItem.owner_id)
            & (MemoryScopeSettingModel.world_id == MemoryItem.world_id)
            & (MemoryScopeSettingModel.subject_world_character_id == MemoryItem.subject_world_character_id),
        ).where(MemoryItem.id.in_(ids), MemoryItem.owner_id == scope.owner_id,
                MemoryItem.world_id == scope.world_id,
                MemoryItem.subject_world_character_id == scope.subject_world_character_id,
                MemoryScopeSettingModel.enabled.is_(True) if require_enabled else True)).all()
        items = {row.id: row for row in rows if _item_retrievable(row, now)}
        if not items:
            return ()
        evidence_rows = self.session.scalars(select(MemoryItemEvidence).where(
            MemoryItemEvidence.memory_item_id.in_(items)).order_by(MemoryItemEvidence.id)).all()
        evidence = {row.id: row for row in evidence_rows}
        info = set(self.session.scalars(select(MemoryEpisodeInfo.memory_item_id).where(
            MemoryEpisodeInfo.memory_item_id.in_(items))))
        units = self.session.scalars(select(MemoryEpisodeUnit).where(
            MemoryEpisodeUnit.memory_item_id.in_(items)).order_by(MemoryEpisodeUnit.ordinal, MemoryEpisodeUnit.id)).all()
        links = self.session.scalars(select(MemoryEpisodeUnitEvidence).where(
            MemoryEpisodeUnitEvidence.unit_id.in_([u.id for u in units])).order_by(MemoryEpisodeUnitEvidence.ordinal)).all() if units else ()
        links_by_unit = {}
        for link in links:
            links_by_unit.setdefault(link.unit_id, []).append(link)
        thought_refs = {unit.id: f"chat:{unit.chat_thought_message_id}" if unit.chat_thought_message_id is not None
                        else f"social:{unit.social_thought_id}" if unit.social_thought_id else None for unit in units}
        # Readers must propagate DB errors. An absent mapping entry only means a
        # completed lookup found no accessible canonical record.
        sources = self.reader.read_sources(scope=scope, identities=tuple(dict.fromkeys(
            (row.source_type, row.source_id) for row in evidence_rows)))
        thoughts = self.reader.read_thoughts(scope=scope, references=tuple(dict.fromkeys(
            ref for ref in thought_refs.values() if ref)))

        def source(row, role, start=0, end=None):
            identity = row.source_type, row.source_id
            current = sources.get(identity)
            status, text = "missing", None
            if current is not None:
                blocked = memory_evidence_blocked_code(scope=scope, source_type=MemorySourceTypeV1(row.source_type),
                    source_id=row.source_id, evidence=current.evidence)
                if blocked:
                    status = "unavailable"
                elif current.evidence.source_digest != row.source_digest:
                    status = "changed"
                elif start < 0 or (end is not None and (end < start or end > len(current.text))):
                    status = "changed"
                else:
                    status, text = "verified", current.text[start:end]
            return EpisodePacketSource(f"{row.source_type}:{row.source_id}", role, text, status, start, end)

        packet_units = {item_id: [] for item_id in items}
        for unit in units:
            unit_sources = []
            legacy = None
            for link in links_by_unit.get(unit.id, ()):
                row = evidence.get(link.evidence_id)
                # Corrupt cross-item links cannot borrow another memory's scope.
                if row is None or row.memory_item_id != unit.memory_item_id:
                    unit_sources.append(EpisodePacketSource(f"missing-evidence:{link.evidence_id}", link.role, None, "missing"))
                else:
                    material = source(row, link.role, link.start_offset, link.end_offset)
                    unit_sources.append(material)
                    current = sources.get((row.source_type, row.source_id))
                    if material.status == "verified" and current.evidence.actor_world_character_id == scope.subject_world_character_id:
                        legacy = legacy or current.evidence.subjective_context
            reference = thought_refs[unit.id]
            thought = thoughts.get(reference, ActivityThought())
            if reference and reference in thoughts:
                digest = sha256(json.dumps(asdict(thought), sort_keys=True).encode()).hexdigest()
                if digest != unit.thought_digest:
                    thought = ActivityThought(status="invalid")
            packet_units[unit.memory_item_id].append(EpisodePacketUnit(
                unit.id, tuple(unit_sources), thought, reference, unit.coverage, None if reference else legacy))
        for row in evidence_rows:
            if row.memory_item_id not in info:
                material = source(row, "legacy_source")
                current = sources.get((row.source_type, row.source_id))
                legacy = current.evidence.subjective_context if material.status == "verified" and current.evidence.actor_world_character_id == scope.subject_world_character_id else None
                packet_units[row.memory_item_id].append(EpisodePacketUnit(
                    f"legacy:{row.id}", (material,), legacy_subjective_context=legacy))
        # Only visible, currently eligible prior items may be disclosed as links.
        prior_rows = self.session.execute(select(MemoryEpisodeLink.following_item_id, MemoryItem).join(
            MemoryItem, MemoryItem.id == MemoryEpisodeLink.prior_item_id,
        ).where(MemoryEpisodeLink.following_item_id.in_(items), MemoryItem.owner_id == scope.owner_id,
                MemoryItem.world_id == scope.world_id,
                MemoryItem.subject_world_character_id == scope.subject_world_character_id)).all()
        priors = {}
        for following, prior in prior_rows:
            if _item_retrievable(prior, now):
                priors.setdefault(following, []).append(prior.id)
        return tuple(EpisodePacket(identifier, items[identifier].summary,
            "episode_v1" if identifier in info else "legacy_summary", tuple(packet_units[identifier]),
            tuple(sorted(priors.get(identifier, ())))) for identifier in ids if identifier in items)
