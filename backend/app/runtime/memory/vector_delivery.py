"""Prepared identities and replayable, per-item projection writes."""
from dataclasses import dataclass, field
from datetime import UTC
import hashlib
from app.core.sqlite_concurrency import run_sqlite_session_immediate, is_sqlite_contention
from app.core.result_journal import ResultJournalError
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument
from app.domains.memory.repository.vector_work import read_work, retained_registration
from app.runtime.memory_embedding_provider import embedding_material, validate_embedding_credential
from app.runtime.memory.sqlite_vec1 import vector_blob, MemoryVectorProjectionError


@dataclass(frozen=True)
class PreparedVector:
    item_id: str
    work: tuple
    document: object = field(repr=False)
    material: object = field(repr=False)
    revision: int
    attempt_revision: str
    binding: str

    @property
    def group(self):
        return self.work[0], self.work[1], self.revision, self.attempt_revision


def prepare(projection, item_id, documents, credential_revision):
    with projection._factory() as session:
        work = read_work(session, item_id)
        if work is None:
            retained = retained_registration(session, item_id)
            if not retained:
                projection.index.delete(f"memory-item:{item_id}")
                projection.journal.remove_item(item_id)
            return "disabled" if retained else "ineligible"
        scope, config, digest, version = work
        document = next((doc for doc in documents if doc.kind is RecallDocumentKind.MEMORY_ITEM), None)
        if document is None or hashlib.sha256(document.text.encode()).hexdigest() != digest:
            projection.index.delete(f"memory-item:{item_id}")
            projection.journal.remove_item(item_id)
            return "source_unavailable"
        revision = validate_embedding_credential(session, scope, revision=credential_revision)
        material = embedding_material(session, scope, revision=revision)
    attempt_revision = hashlib.sha256(f"{config.credential_id}:{revision}:{material.fingerprint}".encode()).hexdigest()
    # Store only this digest and the returned vector, not summaries or keys.
    binding = hashlib.sha256(repr((work, document, revision, attempt_revision)).encode()).hexdigest()
    return PreparedVector(item_id, work, document, material, revision, attempt_revision, binding)


def persist(projection, prepared, received):
    scope, config, digest, version = prepared.work
    item_id, doc_id = prepared.item_id, f"memory-item:{prepared.item_id}"
    if projection._closing:
        return "deferred"
    if received["binding"] != prepared.binding:
        projection.journal.remove(scope.world_id, item_id)
        projection._received.pop(item_id, None)
        return "changed"
    vector_blob(received["vector"])
    try:
        projection.journal.write(scope.world_id, item_id, received)
        with projection._factory() as session:
            def apply():
                if projection._closing or read_work(session, item_id) != prepared.work:
                    return "changed"
                current = embedding_material(session, scope, revision=prepared.revision)
                if current.fingerprint != prepared.material.fingerprint:
                    return "changed"
                fresh = projection._source.documents_for_item_ids((item_id,), session=session).get(item_id, ())
                if prepared.document not in fresh:
                    return "changed"
                occurred = prepared.document.occurred_at
                if occurred.tzinfo is None:
                    occurred = occurred.replace(tzinfo=UTC)
                projection.index.upsert((MemoryVectorDocument(doc_id, item_id, scope, version, digest,
                    config.profile, received["vector"], occurred, prepared.document.counterpart_world_character_id,
                    prepared.document.thread_id),))
                return "indexed"
            outcome = run_sqlite_session_immediate(session, apply, require_clean=True)
        projection._finish_attempt(doc_id, config.profile, digest, prepared.attempt_revision, terminal=False)
        projection.journal.remove(scope.world_id, item_id)
        projection._received.pop(item_id, None)
        return outcome
    except ResultJournalError as exc:
        if str(exc) in {"result_journal_world_closed", "result_journal_item_closed"}:
            projection._received.pop(item_id, None)
            return "changed"
        projection.last_code = str(exc)
        return "local_result_pending"
    except Exception as exc:
        if is_sqlite_contention(exc) or isinstance(exc, OSError):
            projection.last_code = "memory_embedding_storage_pending"
            return "local_result_pending"
        # Permission/config changes are not retryable storage errors.
        from app.domains.memory.exceptions import MemoryValidationError
        if isinstance(exc, MemoryValidationError):
            projection.journal.remove(scope.world_id, item_id)
            projection._received.pop(item_id, None)
            return "changed"
        raise


def refresh_current(projection, prepared):
    scope, config, digest, version = prepared.work
    with projection._factory() as session:
        def refresh():
            if projection._closing or read_work(session, prepared.item_id) != prepared.work:
                return "changed"
            current = embedding_material(session, scope, revision=prepared.revision)
            fresh = projection._source.documents_for_item_ids((prepared.item_id,), session=session).get(prepared.item_id, ())
            if current.fingerprint != prepared.material.fingerprint or prepared.document not in fresh:
                return "changed"
            occurred = prepared.document.occurred_at
            projection.index.refresh_version(f"memory-item:{prepared.item_id}", content_hash=digest,
                version=version, scope=scope, occurred_at=occurred.replace(tzinfo=UTC) if occurred.tzinfo is None else occurred,
                counterpart_world_character_id=prepared.document.counterpart_world_character_id, thread_id=prepared.document.thread_id)
            return "current"
        return run_sqlite_session_immediate(session, refresh, require_clean=True)
