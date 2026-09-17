"""Atomic episode application, with current-source and job fences supplied by the owner."""

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime, timedelta
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domains.memory.contracts.episode import EpisodeBundle, EpisodeSelection, EPISODE_VERSION
from app.domains.memory.contracts.provenance import MemoryKindV1, MemorySourceTypeV1
from app.domains.memory.contracts.scope import MemoryScopeSetting
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.episode import (
    MemoryEpisodeBundle, MemoryEpisodeInfo, MemoryEpisodeUnit, MemoryEpisodeUnitEvidence,
    MemoryEpisodeProcessedUnit, MemoryEpisodeLink,
)
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.policies.episode_bundles import bundle_manifest_hash
from app.domains.memory.policies.episode_selection import parse_episode_selection
from app.domains.memory.repository.items import SqlAlchemyMemoryRepository
from app.domains.memory.repository.capacity import require_new_slot
from app.domains.memory.repository.recall_records import _item_retrievable
from app.domains.memory.repository.vector_eligibility import register_content
from app.domains.memory.service.items import memory_evidence_blocked_code


class SqlAlchemyEpisodeApply:
    def __init__(self, session: Session, memory: SqlAlchemyMemoryRepository):
        self.session, self.memory = session, memory

    def apply(self, *, bundle: EpisodeBundle, selection: EpisodeSelection,
              setting: MemoryScopeSetting, now: datetime,
              revalidate: Callable[[EpisodeBundle], Mapping[tuple[str, str], CanonicalMemoryEvidence]],
              job_fence: Callable[[], None]) -> tuple[str, ...]:
        """Flush only; caller commits receipt and queue progress together.

        revalidate must freshly check all source revisions, raw ranges and thought
        ownership/revisions, including skipped/context units. job_fence owns
        consent/profile/activation/lease/cancellation checks. Both run under the
        short application transaction, never while waiting for the provider.
        """
        if bundle.scope != setting.scope or not bundle.activation_epoch:
            raise MemoryValidationError("episode_apply_scope_invalid")
        selection = parse_episode_selection({
            "bundle_ref": bundle.bundle_ref,
            "episodes": [{"summary": p.summary, "source_refs": list(p.source_refs), "follows_episode_refs": list(p.follows_episode_refs)} for p in selection.episodes],
            "skipped_new_refs": list(selection.skipped_new_refs), "needs_split": selection.needs_split,
        }, bundle)
        if selection.needs_split:
            raise MemoryValidationError("episode_apply_requires_split")
        manifest_hash = bundle_manifest_hash(bundle)
        result_hash = sha256(json.dumps(asdict(selection), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with self.session.begin_nested():
            self.session.execute(text("UPDATE memory_scope_settings SET id=id WHERE id=:id"), {"id": setting.id})
            job_fence()
            self.memory.validate_scope(setting.scope)
            self.memory._require_setting(setting)
            if not setting.enabled:
                raise MemoryConflictError("episode_apply_memory_disabled")
            prior_receipt = self.session.scalar(select(MemoryEpisodeBundle).where(
                MemoryEpisodeBundle.scope_setting_id == setting.id,
                MemoryEpisodeBundle.policy_version == EPISODE_VERSION,
                MemoryEpisodeBundle.activation_epoch == bundle.activation_epoch,
                MemoryEpisodeBundle.manifest_hash == manifest_hash,
            ))
            if prior_receipt is not None and prior_receipt.result_hash:
                if prior_receipt.result_hash != result_hash:
                    raise MemoryConflictError("episode_apply_result_conflict")
                return tuple(self.session.scalars(select(MemoryEpisodeInfo.memory_item_id).where(
                    MemoryEpisodeInfo.bundle_id == prior_receipt.id).order_by(MemoryEpisodeInfo.memory_item_id)))
            evidence = revalidate(bundle)
            for unit in bundle.source_refs().values():
                for member in unit.members:
                    row = evidence.get((member.source_type, member.source_id))
                    blocked = memory_evidence_blocked_code(scope=bundle.scope, source_type=MemorySourceTypeV1(member.source_type), source_id=member.source_id, evidence=row)
                    if blocked or row is None or row.source_digest != member.source_digest:
                        raise MemoryConflictError("episode_apply_source_changed")
            for candidate in bundle.prior_episodes:
                prior = self.session.get(MemoryItem, candidate.item_id, populate_existing=True)
                if (prior is None or prior.owner_id != bundle.scope.owner_id or prior.world_id != bundle.scope.world_id
                    or prior.subject_world_character_id != bundle.scope.subject_world_character_id
                    or prior.version != candidate.item_version or prior.summary != candidate.summary
                    or not _item_retrievable(prior, now)
                    or (prior.thread_id is not None and prior.thread_id != bundle.new_units[0].thread_id)):
                    raise MemoryConflictError("episode_apply_prior_changed")
            sources = bundle.source_refs()
            manifest = {ref: {"unit_key": u.unit_key, "unit_revision": u.unit_revision, "coverage": u.coverage,
                              "members": [{k: v for k, v in asdict(m).items() if k != "text"} for m in u.members],
                              "thought_reference": u.thought_reference} for ref, u in sources.items()}
            if prior_receipt is None:
                receipt = MemoryEpisodeBundle(id=str(uuid4()), scope_setting_id=setting.id,
                    policy_version=EPISODE_VERSION, activation_epoch=bundle.activation_epoch,
                    cutoff_sequence=bundle.cutoff_sequence, manifest_hash=manifest_hash,
                    manifest_json=json.dumps(manifest, ensure_ascii=False, sort_keys=True), result_hash=result_hash, created_at=now)
                self.session.add(receipt)
            else:
                from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
                value = SqlAlchemyEpisodeWork._read(prior_receipt)
                if value["state"] != "running" or not value["calls"]:
                    raise MemoryConflictError("episode_apply_work_not_running")
                # Completed input identities and queue progress commit together.
                # Keep the durable provider counter and exact input references.
                value["state"] = "completed"
                value["applied_sources"] = manifest
                prior_receipt.manifest_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
                prior_receipt.result_hash = result_hash
                receipt = prior_receipt
            self.session.flush()
            item_ids = []
            used = set()
            for proposal in selection.episodes:
                require_new_slot(self.session, setting, now=now)
                selected = [sources[ref] for ref in proposal.source_refs]
                first_member = selected[0].members[0]
                first = evidence[(first_member.source_type, first_member.source_id)]
                item = self.memory._new_item(setting=setting, evidence=first,
                    memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT, summary=proposal.summary,
                    confidence=1.0, salience=0.5, valid_from=min(u.occurred_at for u in selected),
                    valid_until=now + timedelta(days=setting.retention_days))
                counterparts = {evidence[(m.source_type, m.source_id)].counterpart_world_character_id for u in selected for m in u.members}
                item.counterpart_world_character_id = next(iter(counterparts)) if len(counterparts) == 1 else None
                self.session.add(item)
                self.session.flush()
                self.session.add(MemoryEpisodeInfo(memory_item_id=item.id, bundle_id=receipt.id, policy_version=EPISODE_VERSION))
                evidence_rows = {}
                for ordinal, unit in enumerate(selected):
                    ref = unit.thought_reference or ""
                    unit_row = MemoryEpisodeUnit(id=str(uuid4()), memory_item_id=item.id,
                        unit_key=unit.unit_key, unit_revision=unit.unit_revision, kind=unit.kind, ordinal=ordinal,
                        coverage=unit.coverage, chat_thought_message_id=int(ref[5:]) if ref.startswith("chat:") else None,
                        social_thought_id=ref[7:] if ref.startswith("social:") else None,
                        thought_digest=sha256(json.dumps(asdict(unit.thought), sort_keys=True).encode()).hexdigest() if ref else None)
                    if ref and not ref.startswith(("chat:", "social:")):
                        raise MemoryValidationError("episode_thought_reference_invalid")
                    self.session.add(unit_row)
                    self.session.flush()
                    for position, member in enumerate(unit.members):
                        key = (member.source_type, member.source_id)
                        if key not in evidence_rows:
                            evidence_rows[key] = self.memory._new_evidence(item.id, evidence[key])
                            self.session.add(evidence_rows[key])
                            self.session.flush()
                        self.session.add(MemoryEpisodeUnitEvidence(unit_id=unit_row.id, evidence_id=evidence_rows[key].id,
                            start_offset=member.start_offset, end_offset=member.start_offset + len(member.text), role=member.role, ordinal=position))
                for ref in proposal.follows_episode_refs:
                    prior = bundle.prior_episodes[int(ref[1:]) - 1]
                    self.session.add(MemoryEpisodeLink(prior_item_id=prior.item_id, following_item_id=item.id, created_at=now))
                register_content(self.session, item, now=now)
                self.session.flush()
                item_ids.append(item.id)
                used.update(proposal.source_refs)
            for ref, unit in sources.items():
                if ref.startswith("S"):
                    self.session.add(MemoryEpisodeProcessedUnit(id=str(uuid4()), bundle_id=receipt.id,
                        scope_setting_id=setting.id, policy_version=EPISODE_VERSION, activation_epoch=bundle.activation_epoch,
                        unit_key=unit.unit_key, unit_revision=unit.unit_revision, decision="used" if ref in used else "skipped"))
            if item_ids:
                self.memory._invalidate_hot_briefs(setting.id, now=now)
                self.memory._enqueue_job(setting.id, reason="episode_bundle_applied", idempotency_key=f"episode:{receipt.id}")
            self.session.flush()
            return tuple(sorted(item_ids))
