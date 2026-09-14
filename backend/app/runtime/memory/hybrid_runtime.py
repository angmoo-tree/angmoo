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


class UnavailableVectorAxis:
    async def search(self, request, *, deadline):
        return HybridAxisResult((), RecallAxisReceipt("vector", RecallAxisStatus.UNAVAILABLE,
            False, 0, 0, "memory_vector_resources_unavailable"))


class MemoryHybridRuntime:
    def __init__(self, session_factory, fts_index, data_paths):
        self._factory = session_factory
        self.projection = None
        self.vector_axis = UnavailableVectorAxis()
        self.status = "stopped"
        self.fts = FtsHybridAxis(FtsReadWorkers(database_path=fts_index.database_path, settings=fts_index.settings))
        self.service = HybridRecallService(fts=self.fts, vector=self,
            canonical=SqlAlchemyHybridCanonicalReader(session_factory, source_reader_factory=source_evidence_reader,
                canonical=canonical_recall_repository(session_factory)))
        self._generations = VectorGenerations(data_paths.search / "memory-vectors", bundled_vector_index)

    async def search(self, request, *, deadline):
        return await self.vector_axis.search(request, deadline=deadline)

    def read_status(self):
        if self.status == "ready" and self.projection is not None and self.projection.status == "degraded":
            return "degraded"
        return self.status

    async def start(self):
        try:
            active, staging = self._generations.open()
            index = staging or active
            if active is not None:
                self._bind(active)
            projection = MemoryVectorProjection(self._factory, index,
                on_clean_cycle=self._promote if staging is not None else None)
            await projection.start()
            self.projection = projection
            self.status = "recovering" if staging is not None else "ready"
        except (MemoryVectorProjectionError, OSError, ValueError):
            self.status = "vector_unavailable"

    def _bind(self, index):
        self.vector_axis = VectorHybridAxis(VectorReadWorkers(database_path=index.database_path,
            extension_path=index._extension, extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest(),
            generation=index.generation), MemoryQueryEmbedder(self._factory,
                lambda session: MemoryEmbeddingRepository(session, memory_repository(session))))

    def _promote(self, index):
        self._generations.promote(index)
        self._bind(index)
        self.status = "ready"

    async def stop(self):
        if self.projection is not None:
            await self.projection.stop()
        self.vector_axis = UnavailableVectorAxis()
        self.status = "stopped"
