"""Projection identities are checked against fresh, bounded canonical documents."""
from datetime import UTC, datetime
import hashlib
from app.contracts.search_diagnostics import collector, lineage, record_identity
from sqlalchemy import select

from app.domains.memory.contracts.hybrid_recall import HybridSourceReceipt, RecallAxisStatus
from app.domains.memory.contracts.recall import MemoryRecallCandidate
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence
from app.domains.memory.repository.recall import SqlAlchemyMemoryRecallDocumentSource
from app.domains.memory.repository.recall_records import _item_scope


class SqlAlchemyHybridCanonicalReader:
    def __init__(self, session_factory, *, source_reader_factory, canonical):
        self._factory, self._reader, self._canonical = session_factory, source_reader_factory, canonical

    def revalidate(self, request, candidates):
        if len(candidates) > 50:
            raise ValueError("hybrid_candidate_limit")
        accepted = []
        rejection_reasons = {}
        scope_rejected = set()
        with self._factory() as session:
            reader = self._reader(session)
            documents = {}
            for item_id in dict.fromkeys(row.candidate.memory_item_id for row in candidates):
                item = session.get(MemoryItem, item_id)
                if item is None or _item_scope(item) != request.scope:
                    if item is not None:
                        scope_rejected.add(item_id)
                    continue
                evidences = list(session.scalars(select(MemoryItemEvidence).where(
                    MemoryItemEvidence.memory_item_id == item.id).order_by(MemoryItemEvidence.id).limit(20)))
                for document in SqlAlchemyMemoryRecallDocumentSource._documents_for_item(
                    session=session, reader=reader, item=item, evidences=evidences, now=datetime.now(UTC)):
                    documents[document.document_id] = document
            for ranked in candidates:
                doc = documents.get(ranked.candidate.document_id)
                if doc is None or doc.memory_item_id != ranked.candidate.memory_item_id:
                    rejection_reasons[ranked.candidate.document_id] = "scope" if ranked.candidate.memory_item_id in scope_rejected else "missing"
                    continue
                if (int(doc.metadata["item_version"]) != ranked.version
                    or hashlib.sha256(doc.text.encode("utf-8")).hexdigest() != ranked.content_hash):
                    rejection_reasons[ranked.candidate.document_id] = "version"
                    continue
                if doc.kind not in request.kinds:
                    rejection_reasons[ranked.candidate.document_id] = "filter"
                    continue
                if request.counterpart_world_character_id is not None and doc.counterpart_world_character_id != request.counterpart_world_character_id:
                    rejection_reasons[ranked.candidate.document_id] = "filter"
                    continue
                if request.thread_id is not None and doc.thread_id != request.thread_id:
                    rejection_reasons[ranked.candidate.document_id] = "filter"
                    continue
                occurred = doc.occurred_at
                if occurred is None:
                    rejection_reasons[ranked.candidate.document_id] = "missing"
                    continue
                if occurred.tzinfo is None:
                    occurred = occurred.replace(tzinfo=UTC)
                if request.occurred_from and occurred < request.occurred_from:
                    rejection_reasons[ranked.candidate.document_id] = "filter"
                    continue
                if request.occurred_to and occurred >= request.occurred_to:
                    rejection_reasons[ranked.candidate.document_id] = "filter"
                    continue
                accepted.append(MemoryRecallCandidate(doc.document_id, doc.memory_item_id, doc.kind,
                    doc.canonical_source_id, ranked.candidate.score, "", doc.counterpart_world_character_id,
                    doc.thread_id, doc.source_type, doc.source_event_id, occurred, doc.metadata))
        records = self._canonical.revalidate_candidates(scope=request.scope, candidates=tuple(accepted), now=datetime.now(UTC), evidence_limit=20)
        if collector() is not None:
            by_document = {record.reference: record for record in records}
            for ranked in candidates:
                record = by_document.get(ranked.candidate.document_id)
                ids = {"document_ref": ("d", ranked.candidate.document_id), "identity_ref": ("i", ranked.identity)}
                if record is not None:
                    ids.update(record_identity(record))
                lineage("canonical", "accepted" if record is not None else "excluded",
                    reason=None if record is not None else rejection_reasons.get(ranked.candidate.document_id, "validation"), identities=ids)
        return records

    def hydrate(self, request, records):
        # Original text is already validated by revalidate_candidates. Hydrate only
        # exact evidence references authorized by those records; no new search.
        all_refs = tuple(dict.fromkeys(ref for row in records for ref in row.evidence_references))
        refs = all_refs[:20]
        sources = self._canonical.read_exact_sources(scope=request.scope, references=refs, now=datetime.now(UTC))
        by_ref = {row.reference: row for row in sources}
        receipts = tuple(HybridSourceReceipt(ref, RecallAxisStatus.READY if ref in by_ref else RecallAxisStatus.UNAVAILABLE,
            1 if ref in by_ref else 0) for ref in all_refs)
        ordered = list(records)
        existing = {row.reference for row in ordered}
        if collector() is not None:
            for row in records:
                for ref in row.evidence_references[:20]:
                    source = by_ref.get(ref)
                    if source is not None:
                        ids = record_identity(source)
                        ids["related_ref"] = ("r", row.reference)
                        lineage("hydrate", "linked", identities=ids)
        for ref in refs:
            if ref in by_ref and ref not in existing:
                ordered.append(by_ref[ref])
                lineage("hydrate", "added", identities=record_identity(by_ref[ref]))
            elif ref in by_ref:
                lineage("hydrate", "existing", identities=record_identity(by_ref[ref]))
            else:
                lineage("hydrate", "missing", identities={"record_ref": ("r", ref)})
        return tuple(ordered), receipts
