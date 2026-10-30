"""Application-owned shared worker limits and optional vector lifecycle."""
from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.repository.hybrid_recall import SqlAlchemyHybridCanonicalReader
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.memory.vector_resources import bundled_vector_index
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.runtime.memory.vector_generations import VectorGenerations
from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError
from app.runtime.memory.recall_composition import canonical_recall_repository
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory_embedding_provider import MemoryQueryEmbedder
from app.runtime.memory.composition import memory_repository
from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
import hashlib
import asyncio
from time import monotonic
from app.runtime.memory.search_worker_pool import SearchWorkerControl


class UnavailableVectorAxis:
    async def search(self, request, *, deadline):
        return HybridAxisResult((), RecallAxisReceipt("vector", RecallAxisStatus.UNAVAILABLE,
            False, 0, 0, "memory_vector_resources_unavailable"))


class MemoryHybridRuntime:
    def __init__(self, session_factory, fts_index, data_paths, *, fts_policy="legacy_strict_v1", episode_only=False,fts_workers=None,vector_generations=None,separate_canonical_guard=False):
        self._factory = session_factory
        from app.runtime.memory.canonical_worker import DeadlineSessionFactory, CanonicalReadWorker
        canonical_sessions = DeadlineSessionFactory(session_factory)
        self._episode_only = episode_only
        self._search_control = SearchWorkerControl()
        self._transition = None
        self._stopping = False
        self.projection = None
        self.vector_axis = UnavailableVectorAxis()
        self.status = "stopped"
        self.fts = FtsHybridAxis(fts_workers or FtsReadWorkers(database_path=fts_index.database_path,
            settings=fts_index.settings, control=self._search_control), lexical_policy=fts_policy)
        if episode_only:
            from app.domains.memory.repository.episode_hybrid_recall import SqlAlchemyEpisodeHybridReader
            from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
            reader = SqlAlchemyEpisodeHybridReader(canonical_sessions, detail_reader_factory=RuntimeEpisodeDetailReader,
                access_observer=canonical_sessions.record_access, phase=canonical_sessions.phase)
        else:
            reader = SqlAlchemyHybridCanonicalReader(canonical_sessions, source_reader_factory=source_evidence_reader,
                canonical=canonical_recall_repository(canonical_sessions))
        self.canonical_worker = CanonicalReadWorker(canonical_sessions, reader,
            separate_guard=separate_canonical_guard)
        self.service = HybridRecallService(fts=self.fts, vector=self, canonical=self.canonical_worker)
        self._generations = vector_generations or VectorGenerations(data_paths.search / "memory-vectors", bundled_vector_index)

    async def search(self, request, *, deadline):
        if self._transition is not None:
            async with asyncio.timeout(max(0, deadline - monotonic())):
                await asyncio.shield(self._transition)
        return await self.vector_axis.search(request, deadline=deadline)

    def request_preparation(self, *, semantic=True):
        """Readiness only; caller owns current scope/settings authorization."""
        fts = self.fts._workers.request_preparation()
        vector = {"status": "disabled", "reason": None}
        if semantic:
            if self._transition is not None and not self._transition.done():
                vector = {"status": "preparing", "reason": "memory_vector_generation_transition"}
            elif isinstance(self.vector_axis, VectorHybridAxis):
                vector = self.vector_axis._workers.request_preparation()
            else:
                vector = {"status": "unavailable", "reason": "memory_vector_resources_unavailable"}
        return {"fts": fts, "vector": vector}

    def read_status(self):
        if self.status == "ready" and self.projection is not None:
            return self.projection.status
        return self.status

    def erase_items(self, identifiers):
        """Remove exact registrations from every retained disposable generation."""
        from app.runtime.received_results import result_journal
        identifiers = tuple(identifiers)
        journal = result_journal("memory-embedding")
        for identifier in identifiers:
            journal.close_item(identifier)
        root = self._generations.root / "generations"
        try:
            generations = tuple(root.iterdir())
        except FileNotFoundError:
            return
        # Permission/IO failure must propagate instead of an empty glob being
        # mistaken for a completed erasure. Never follow external links.
        for directory in generations:
            if directory.is_symlink() or directory.is_junction():
                raise ValueError("memory_vector_generation_link")
            path = directory / "vectors.sqlite3"
            try:
                path.stat()
            except FileNotFoundError:
                continue
            index = self._generations._index(path.parent.name)
            index.open()
            index.erase_items(identifiers)

    async def start(self):
        projection = None
        try:
            active, staging = self._generations.open()
            index = staging or active
            if staging is not None and active is None:
                previous = self._generations.state["active"]
                try:
                    (self._generations.root / "generations" / previous / "vectors.sqlite3").stat()
                except FileNotFoundError:
                    from app.domains.memory.models.vector_work import MemoryVectorMaintenance
                    with self._factory() as session:
                        if session.get(MemoryVectorMaintenance, previous) is None:
                            # Pre-migration budgets were stored in that file.
                            # Missing evidence cannot authorize another paid call.
                            raise MemoryVectorProjectionError("memory_vector_legacy_budget_missing") from None
            if active is not None:
                self._bind(active)
            projection = MemoryVectorProjection(self._factory, index,
                on_clean_cycle=self._promote if staging is not None else None, episode_only=self._episode_only,
                retained_indexes=self._retained_indexes)
            await projection.start()
            self.projection = projection
            self.status = "recovering" if staging is not None else "ready"
        except (MemoryVectorProjectionError, OSError, ValueError):
            if projection is not None:
                await projection.stop()
            self.status = "vector_unavailable"

    def _bind(self, index):
        self.vector_axis = VectorHybridAxis(VectorReadWorkers(database_path=index.database_path,
            extension_path=index._extension, extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest(),
            generation=index.generation, control=self._search_control), MemoryQueryEmbedder(self._factory,
                lambda session: MemoryEmbeddingRepository(session, memory_repository(session))))

    def _retained_indexes(self):
        root = self._generations.root / "generations"
        for directory in root.iterdir():
            if directory.is_symlink() or directory.is_junction():
                raise ValueError("memory_vector_generation_link")
            try:
                (directory / "vectors.sqlite3").stat()
            except FileNotFoundError:
                continue
            yield self._generations._index(directory.name)

    def _promote(self, index):
        if self._stopping:
            return
        self._generations.promote(index)
        old = self.vector_axis

        async def replace_binding():
            if isinstance(old, VectorHybridAxis):
                await old._workers.stop()
            if not self._stopping:
                self._bind(index)
                self.status = "ready"
        # Projection's callback is synchronous. Own the transition explicitly;
        # reads await it and shutdown drains it before disposing database owners.
        self._transition = asyncio.create_task(replace_binding())

    async def stop(self):
        self._stopping = True
        errors = []
        async def drain(operation):
            try:
                await operation
            except Exception as exc:
                errors.append(exc)
        await drain(self.fts._workers.stop())
        if self._transition is not None:
            await drain(asyncio.shield(self._transition))
        if isinstance(self.vector_axis, VectorHybridAxis):
            await drain(self.vector_axis._workers.stop())
        await drain(self.canonical_worker.stop())
        if self.projection is not None:
            await drain(self.projection.stop())
        if errors:
            self.status = "cleanup_failed"
            # Retain quarantined ownership. Do not report stopped or dispose
            # the control executor while an OS process may still be starting.
            raise ExceptionGroup("memory_runtime_cleanup_failed", errors)
        self.vector_axis = UnavailableVectorAxis()
        self.status = "stopped"
        self._search_control.close()
