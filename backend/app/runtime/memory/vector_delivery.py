"""Snapshot preparation followed by a bounded canonical-to-Vec1 effect fence."""
from app.core import work_observation as observation
from dataclasses import dataclass, field
from contextlib import nullcontext
from datetime import UTC
import hashlib
from sqlalchemy import select, text
from app.core.sqlite_concurrency import run_sqlite_session_immediate, is_sqlite_contention
from app.core.result_journal import ResultJournalError
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument
from app.domains.memory.models.vector_work import MemoryVectorDependency
from app.domains.memory.repository.vector_work import read_work, retained_registration
from app.domains.memory.repository.vector_queue import owns
from app.runtime.memory.vector_proof import snapshot, current, VectorProof
from app.runtime.memory.sqlite_vec1 import vector_blob


@dataclass(frozen=True)
class PreparedVector:
    item_id: str
    work: tuple
    document: object = field(repr=False)
    material: object = field(repr=False)
    revision: int
    attempt_revision: str
    binding: str
    proof: VectorProof
    claim: object = None
    requested_revision: int | None = None

    @property
    def group(self):
        return self.work[0], self.work[1], self.revision, self.attempt_revision


def _dependencies(projection, item_id, proof):
    operations = []
    for identifier, dependencies in ((item_id, proof.dependencies), *proof.related_dependencies):
        with projection._factory() as session:
            old = set(session.execute(select(MemoryVectorDependency.source_kind, MemoryVectorDependency.source_key)
                .where(MemoryVectorDependency.item_id == identifier)).all())
        if identifier == item_id:
            operations.extend((False, identifier, key) for key in old - dependencies)
        operations.extend((True, identifier, key) for key in dependencies - old)
    for start in range(0, len(operations), 64):
        with projection._factory() as session:
            def apply():
                if not current(session, proof):
                    return False
                for insert, identifier, (kind, key) in operations[start:start + 64]:
                    sql = ("INSERT OR IGNORE INTO memory_vector_dependencies(item_id,source_kind,source_key) VALUES (:item,:kind,:key)" if insert
                        else "DELETE FROM memory_vector_dependencies WHERE item_id=:item AND source_kind=:kind AND source_key=:key")
                    session.execute(text(sql), dict(item=identifier, kind=kind, key=key))
                return True
            if not run_sqlite_session_immediate(session, apply, require_clean=True):
                return False
    return True


def prepare(projection, item_id, documents, credential_revision):
    work, documents, material, revision, retained, proof = snapshot(projection, item_id, credential_revision)
    if proof.world_closed:
        return "world_closed"  # Dedicated erasure owns all files and work cleanup.
    projection._boundaries[item_id] = proof.next_boundary
    if not _dependencies(projection, item_id, proof):
        return "changed"
    if isinstance(material, Exception):
        raise material
    document = next((doc for doc in documents if doc.kind is RecallDocumentKind.MEMORY_ITEM), None)
    outcome = None
    if work is None:
        outcome = ("disabled" if document is not None else "source_unavailable") if retained else "ineligible"
    elif document is None or hashlib.sha256(document.text.encode()).hexdigest() != work[2]:
        outcome = "source_unavailable"
    if outcome is not None:
        if outcome == "disabled":
            return outcome
        world_id = next((key[6:] for key, _ in proof.epochs if key.startswith("world:")), None)
        receipt = projection.journal.read(world_id, item_id) if world_id else None
        for index in projection._retained_indexes():
            factory = getattr(index, "effect_connection", None)
            with (factory() if factory else nullcontext()), projection._factory() as session:
                def remove():
                    if not current(session, proof) or read_work(session, item_id) != work:
                        return "changed"
                    if work is None and retained_registration(session, item_id) != retained:
                        return "changed"
                    if not owns(session, projection._claims.get(item_id)):
                        return "changed"
                    if index.identity(f"memory-item:{item_id}") is not None:
                        index.delete(f"memory-item:{item_id}")
                    return outcome
                outcome = run_sqlite_session_immediate(session, remove, require_clean=True)
            if outcome == "changed":
                break
        if outcome != "changed":
            if world_id and receipt is not None:
                projection.journal.remove(world_id, item_id, expected_payload=receipt)
            elif world_id is None:
                projection.journal.remove_item(item_id)
        return outcome
    scope, config, digest, version = work
    attempt_revision = hashlib.sha256(f"{config.credential_id}:{revision}:{material.fingerprint}".encode()).hexdigest()
    projection._attempt_keys[item_id] = (config.profile, digest, attempt_revision)
    # Metadata changes may reuse a received embedding. Authorization is checked
    # against a fresh source proof before every final effect.
    binding = hashlib.sha256(repr((scope, digest, config.profile, config.provider, config.model, attempt_revision)).encode()).hexdigest()
    return PreparedVector(item_id, work, document, material, revision, attempt_revision, binding,
        proof, projection._claims.get(item_id), credential_revision)


def _effect(projection):
    factory = getattr(projection.index, "effect_connection", None)
    return factory() if factory is not None else nullcontext()


def _valid(projection, session, prepared):
    return (not projection._closing and owns(session, prepared.claim)
        and current(session, prepared.proof) and read_work(session, prepared.item_id) == prepared.work)


def _document(prepared, vector):
    scope, config, digest, version = prepared.work
    occurred = prepared.document.occurred_at
    return MemoryVectorDocument(f"memory-item:{prepared.item_id}", prepared.item_id, scope, version, digest,
        config.profile, vector, occurred.replace(tzinfo=UTC) if occurred.tzinfo is None else occurred,
        prepared.document.counterpart_world_character_id, prepared.document.thread_id)


@observation.observed("vector_persist")
def persist(projection, prepared, received, *, revalidate=True):
    scope, config, digest, version = prepared.work
    item_id, doc_id = prepared.item_id, f"memory-item:{prepared.item_id}"
    if projection._closing:
        return "deferred"
    if received["binding"] != prepared.binding:
        legacy = hashlib.sha256(repr((prepared.work, prepared.document, prepared.revision, prepared.attempt_revision)).encode()).hexdigest()
        if received["binding"] == legacy:
            received = {**received, "binding": prepared.binding}
        else:
            projection.journal.remove(scope.world_id, item_id, expected_payload=received)
            projection._received.pop(item_id, None)
            return "changed"
    vector_blob(received["vector"])
    document = _document(prepared, received["vector"])
    try:
        projection.journal.write(scope.world_id, item_id, received)
        with _effect(projection), projection._factory() as session:
            def apply():
                if not _valid(projection, session, prepared):
                    return "changed"
                if not projection.index.matches(document):
                    projection.index.upsert((document,))
                return "indexed"
            outcome = run_sqlite_session_immediate(session, apply, require_clean=True)
        if outcome == "changed":
            if revalidate and not projection._closing:
                fresh = prepare(projection, item_id, (), prepared.requested_revision)
                if isinstance(fresh, PreparedVector):
                    return persist(projection, fresh, received, revalidate=False)
            return outcome
        projection._finish_attempt(doc_id, config.profile, digest, prepared.attempt_revision, terminal=False)
        projection.journal.remove(scope.world_id, item_id, expected_payload=received)
        projection._received.pop(item_id, None)
        observation.emit("result", boundary="committed", receipt_id=received.get("receipt_id"), item_id=item_id, outcome=outcome)
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
        from app.domains.memory.exceptions import MemoryValidationError
        if isinstance(exc, MemoryValidationError):
            projection.journal.remove(scope.world_id, item_id, expected_payload=received)
            projection._received.pop(item_id, None)
            return "changed"
        raise


def refresh_current(projection, prepared):
    document = _document(prepared, ())
    with _effect(projection), projection._factory() as session:
        def refresh():
            if not _valid(projection, session, prepared):
                return "changed"
            if not projection.index.matches(document):
                projection.index.refresh_version(document.document_id, content_hash=document.content_hash,
                    version=document.version, scope=document.scope, occurred_at=document.occurred_at,
                    counterpart_world_character_id=document.counterpart_world_character_id, thread_id=document.thread_id)
            return "current"
        return run_sqlite_session_immediate(session, refresh, require_clean=True)
