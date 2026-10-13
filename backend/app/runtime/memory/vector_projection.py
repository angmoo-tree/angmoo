"""Incremental, restartable projection from accepted summary registrations."""
import asyncio
from datetime import UTC, datetime
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
    def __init__(self, session_factory, index, *, provider=None, on_clean_cycle=None, episode_only=False):
        self._factory, self.index = session_factory, index
        self._source = recall_document_source(session_factory, episode_only=episode_only)
        self._provider = provider or GeminiAdapter()
        self._cursor = self._cleanup_cursor = ""
        self._task = None
        self._closing = False
        self.status = "stopped"
        self.last_code = None
        self.logical_calls = self.physical_attempts = 0
        # Per-content failures survive the process in the disposable projection.
        self._attempts_ready = False
        self._on_clean_cycle = on_clean_cycle
        self._cycle_clean = True
        self._eligible_clean = self._cleanup_complete = False
        self._tick_failed = False
        from app.runtime.memory.canonical_work import MemoryCanonicalWork
        self._canonical = MemoryCanonicalWork()

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

    async def sync_item(self, item_id, *, credential_revision=None):
        if self._closing:
            return "deferred"
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
        documents = (await self._canonical.call(self._source.documents_for_item_ids, (item_id,))).get(item_id, ())
        if self._closing:
            return "deferred"
        document = next((doc for doc in documents if doc.kind is RecallDocumentKind.MEMORY_ITEM), None)
        if document is None or hashlib.sha256(document.text.encode("utf-8")).hexdigest() != digest:
            self.index.delete(doc_id)
            return "source_unavailable"
        identity = self.index.identity(doc_id)
        if identity and identity[1:] == (digest, config.profile):
            occurred = document.occurred_at
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            self.index.refresh_version(doc_id, content_hash=digest, version=version, scope=scope,
                occurred_at=occurred, counterpart_world_character_id=document.counterpart_world_character_id,
                thread_id=document.thread_id)
            return "current"
        with self._factory() as session:
            from app.runtime.memory_embedding_provider import validate_embedding_credential
            admitted_revision = validate_embedding_credential(session, scope, revision=credential_revision)
            material = embedding_material(session, scope, revision=admitted_revision)
        attempt_revision = hashlib.sha256(f"{config.credential_id}:{admitted_revision}:{material.fingerprint}".encode()).hexdigest()
        if not self._claim_attempt(doc_id, config.profile, digest, attempt_revision):
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
                self._finish_attempt(doc_id, config.profile, digest, attempt_revision, terminal=True)
            self.last_code = "memory_embedding_failed"
            return "failed"
        # Serialize the local projection write with canonical deletion/revocation.
        # The provider wait has already ended; no network IO holds this lock.
        if self._closing:
            return "deferred"
        with self._factory() as session:
            from sqlalchemy import update
            from app.domains.memory.models.items import MemoryScopeSettingModel
            locked = session.execute(update(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.owner_id == scope.owner_id,
                MemoryScopeSettingModel.world_id == scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id == scope.subject_world_character_id,
            ).values(version=MemoryScopeSettingModel.version,
                updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
            if locked.rowcount != 1:
                return "changed"
            if read_work(session, item_id) != work:
                return "changed"
            current = embedding_material(session, scope, revision=admitted_revision)
            if current.fingerprint != material.fingerprint:
                return "changed"
            fresh = self._source.documents_for_item_ids((item_id,), session=session).get(item_id, ())
            if document not in fresh:
                return "changed"
            occurred = document.occurred_at
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            self.index.upsert((MemoryVectorDocument(doc_id, item_id, scope, version, digest, config.profile,
                response.vector, occurred, document.counterpart_world_character_id, document.thread_id),))
            session.commit()
        self._finish_attempt(doc_id, config.profile, digest, attempt_revision, terminal=False)
        return "indexed"

    async def tick(self):
        await self._prepare_page()
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

    async def _prepare_page(self):
        from sqlalchemy import select
        from app.domains.memory.models.activity_configuration import MemoryIndexPreparation
        from app.domains.memory.models.items import MemoryScopeSettingModel
        from app.domains.memory.models.embedding import MemoryEmbeddingSetting
        from app.domains.memory.contracts.scope import MemoryScope
        from app.domains.memory.repository.index_preparation import advance
        from app.runtime.memory_embedding_provider import validate_embedding_credential
        with self._factory() as session:
            ids = tuple(session.scalars(select(MemoryIndexPreparation.scope_setting_id).where(
                MemoryIndexPreparation.state == "running").order_by(MemoryIndexPreparation.scope_setting_id).limit(4)))
        for setting_id in ids:
            with self._factory() as session:
                row = session.get(MemoryIndexPreparation, setting_id)
                setting = session.get(MemoryScopeSettingModel, setting_id)
                if row is None or setting is None or row.state != "running":
                    continue
                scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
                try:
                    if validate_embedding_credential(session, scope, revision=row.credential_revision) != row.credential_revision:
                        raise ValueError("changed")
                    page = advance(session, row, now=datetime.now(UTC))
                    config = session.get(MemoryEmbeddingSetting, setting_id)
                    snapshot = (row.revision, row.source_generation, row.cursor, setting.version,
                        None if config is None else config.version)
                    admitted_revision = row.credential_revision
                except Exception:
                    row.state, row.last_code = "error", "memory_embedding_preparation_changed"
                    session.commit()
                    continue
                if row.state != "running":
                    session.commit()
                    continue
                session.commit()
            complete = True
            for item_id in page:
                try:
                    outcome = await self.sync_item(item_id, credential_revision=admitted_revision)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    complete = False
                    break
                if outcome not in {"indexed", "current", "ineligible", "source_unavailable"}:
                    complete = False
                    break
            with self._factory() as session:
                row = session.get(MemoryIndexPreparation, setting_id)
                if row is None or row.state != "running" or (row.revision, row.source_generation, row.cursor) != snapshot[:3]:
                    continue
                try:
                    setting = session.get(MemoryScopeSettingModel, setting_id)
                    config = session.get(MemoryEmbeddingSetting, setting_id)
                    if (setting is None or config is None or not setting.enabled or not config.enabled or
                        config.profile != row.profile or (setting.version, config.version) != snapshot[3:]):
                        complete = False
                    if validate_embedding_credential(session, scope, revision=row.credential_revision) != row.credential_revision:
                        complete = False
                except Exception:
                    complete = False
                if complete:
                    row.cursor = page[-1] if page else row.cursor
                    if len(page) < 64:
                        row.state, row.last_code = "ready", None
                else:
                    row.state, row.last_code = "error", "memory_embedding_preparation_failed"
                session.commit()

    async def start(self):
        self._closing = False
        if self._canonical.closed:
            from app.runtime.memory.canonical_work import MemoryCanonicalWork
            self._canonical = MemoryCanonicalWork()
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

    def fence(self):
        self._closing = True
        if self._task is not None:
            self._task.cancel()

    async def stop(self):
        self.fence()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "stopped"
        await self._canonical.drain()
        self._canonical.close()
