"""Incremental, restartable projection from accepted summary registrations."""
import asyncio
from datetime import UTC
import hashlib
from time import time

from app.domains.memory.contracts.embedding import EMBEDDING_DIMENSIONS, embedding_text
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument
from app.domains.memory.repository.vector_work import eligible_page, read_work, retained_registration
from app.providers.contracts import EmbeddingRequest
from app.providers.gemini import GeminiAdapter
from app.runtime.memory.recall_composition import recall_document_source
from app.runtime.memory_embedding_provider import embedding_material


class MemoryVectorProjection:
    def __init__(self, session_factory, index, *, provider=None, on_clean_cycle=None):
        self._factory, self.index = session_factory, index
        self._source = recall_document_source(session_factory)
        self._provider = provider or GeminiAdapter()
        self._cursor = self._cleanup_cursor = ""
        self._task = None
        self.status = "stopped"
        self.last_code = None
        self.logical_calls = self.physical_attempts = 0
        # Per-content failures survive the process in the disposable projection.
        self._attempts_ready = False
        self._on_clean_cycle = on_clean_cycle
        self._cycle_clean = True
        self._eligible_clean = self._cleanup_complete = False
        self._tick_failed = False

    def _prepare_attempts(self):
        if self._attempts_ready:
            return
        with self.index._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS embedding_attempts_v2 (document_id TEXT NOT NULL, profile TEXT NOT NULL, content_hash TEXT NOT NULL, credential_revision TEXT NOT NULL, attempts INTEGER NOT NULL, code TEXT, retry_after REAL NOT NULL, PRIMARY KEY(document_id,profile,content_hash,credential_revision))")
            connection.commit()
        self._attempts_ready = True

    def _claim_attempt(self, doc_id, profile, digest, credential_revision):
        self._prepare_attempts()
        with self.index._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            key = (doc_id, profile, digest, credential_revision)
            old = connection.execute("SELECT attempts,code,retry_after FROM embedding_attempts_v2 WHERE document_id=? AND profile=? AND content_hash=? AND credential_revision=?", key).fetchone()
            if old and (old[0] >= 3 or old[1] == "terminal" or old[2] > time()):
                return False
            count = old[0] + 1 if old else 1
            connection.execute("INSERT INTO embedding_attempts_v2 VALUES(?,?,?,?,?,NULL,?) ON CONFLICT(document_id,profile,content_hash,credential_revision) DO UPDATE SET attempts=excluded.attempts,code=NULL,retry_after=excluded.retry_after", (*key, count, time() + 30 * 2 ** (count - 1)))
            connection.commit()
        return True

    def _finish_attempt(self, doc_id, profile, digest, credential_revision, *, terminal):
        with self.index._connect() as connection:
            if terminal:
                connection.execute("UPDATE embedding_attempts_v2 SET code='terminal' WHERE document_id=? AND profile=? AND content_hash=? AND credential_revision=?", (doc_id, profile, digest, credential_revision))
            else:
                connection.execute("DELETE FROM embedding_attempts_v2 WHERE document_id=? AND profile=? AND content_hash=?", (doc_id, profile, digest))
            connection.commit()

    async def sync_item(self, item_id):
        with self._factory() as session:
            work = read_work(session, item_id)
        doc_id = f"memory-item:{item_id}"
        if work is None:
            with self._factory() as session:
                retained = retained_registration(session, item_id)
            if not retained:
                self.index.delete(doc_id)
            return "disabled" if retained else "ineligible"
        scope, config, digest, version = work
        documents = self._source.documents_for_item_ids((item_id,)).get(item_id, ())
        document = next((doc for doc in documents if doc.kind is RecallDocumentKind.MEMORY_ITEM), None)
        if document is None or hashlib.sha256(document.text.encode("utf-8")).hexdigest() != digest:
            self.index.delete(doc_id)
            return "source_unavailable"
        identity = self.index.identity(doc_id)
        if identity and identity[1:] == (digest, config.profile):
            self.index.refresh_version(doc_id, content_hash=digest, version=version)
            return "current"
        with self._factory() as session:
            material = embedding_material(session, scope.owner_id, config.credential_id)
        credential_revision = hashlib.sha256(f"{config.credential_id}:{material.fingerprint}".encode()).hexdigest()
        if not self._claim_attempt(doc_id, config.profile, digest, credential_revision):
            return "attempts_exhausted"
        self.logical_calls += 1
        try:
            response = await self._provider.embed_measured(EmbeddingRequest(material.reveal(), config.model,
                embedding_text(document.text, query=False), EMBEDDING_DIMENSIONS), timeout_seconds=30)
            if self.physical_attempts is not None:
                self.physical_attempts += response.physical_attempts
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            attempts = getattr(exc, "physical_attempts", None)
            self.physical_attempts = (None if attempts is None or self.physical_attempts is None
                                      else self.physical_attempts + attempts)
            if not getattr(exc, "retryable", False):
                self._finish_attempt(doc_id, config.profile, digest, credential_revision, terminal=True)
            self.last_code = "memory_embedding_failed"
            return "failed"
        # Re-open canonical state and the chosen credential after the API wait.
        with self._factory() as session:
            if read_work(session, item_id) != work:
                return "changed"
            current = embedding_material(session, scope.owner_id, config.credential_id)
            if current.fingerprint != material.fingerprint:
                return "changed"
        fresh = self._source.documents_for_item_ids((item_id,)).get(item_id, ())
        if document not in fresh:
            return "changed"
        occurred = document.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        self.index.upsert((MemoryVectorDocument(doc_id, item_id, scope, version, digest, config.profile,
            response.vector, occurred, document.counterpart_world_character_id, document.thread_id),))
        self._finish_attempt(doc_id, config.profile, digest, credential_revision, terminal=False)
        return "indexed"

    async def tick(self):
        self._tick_failed = False
        if not self._cursor:
            self._eligible_clean = False
        with self._factory() as session:
            ids = eligible_page(session, after=self._cursor)
        for item_id in ids:
            outcome = await self.sync_item(item_id)
            if outcome not in {"indexed", "current", "disabled", "ineligible", "source_unavailable"}:
                self._cycle_clean = False
                self._eligible_clean = False
                self._tick_failed = True
            self._cursor = item_id
            await asyncio.sleep(0)
        if len(ids) < 64:
            self._cursor = ""
        rows = self.index.document_page(after=self._cleanup_cursor)
        for doc_id, item_id in rows:
            with self._factory() as session:
                eligible = retained_registration(session, item_id)
            if not eligible:
                self.index.delete(doc_id)
            self._cleanup_cursor = doc_id
        if len(rows) < 64:
            self._cleanup_cursor = ""
            self._cleanup_complete = True
        if len(ids) < 64:
            self._eligible_clean = self._cycle_clean
            self._cycle_clean = True
        if self._eligible_clean and self._cleanup_complete and self._on_clean_cycle is not None:
            self._on_clean_cycle(self.index)
            self._on_clean_cycle = None

    async def start(self):
        self.index.open()
        self.status = "ready"
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            try:
                await self.tick()
                self.status = "degraded" if self._tick_failed else "ready"
            except asyncio.CancelledError:
                raise
            except Exception:
                self.status, self.last_code = "degraded", "memory_vector_projection_failed"
            await asyncio.sleep(1)

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "stopped"
