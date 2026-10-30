"""Keep hybrid fusion/currentness while replacing its persistence adapters."""
from app.runtime.memory.hybrid_runtime import MemoryHybridRuntime
from app.runtime.memory.postgresql_generations import PostgresVectorGenerations
from app.runtime.memory.postgresql_workers import PostgresReadWorkers
from app.runtime.memory.hybrid_axes import VectorHybridAxis
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.runtime.memory_embedding_provider import MemoryQueryEmbedder
from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
from app.runtime.memory.composition import memory_repository


class PostgresMemoryHybridRuntime(MemoryHybridRuntime):
    def __init__(self,session_factory,fts_index,data_paths,**kwargs):
        super().__init__(session_factory,fts_index,data_paths,
            separate_canonical_guard=True,
            fts_workers=PostgresReadWorkers(fts_index,axis='fts'),
            vector_generations=PostgresVectorGenerations(fts_index.engine),**kwargs)
    def _bind(self,index):
        self.vector_axis=VectorHybridAxis(PostgresReadWorkers(index,axis='vector'),MemoryQueryEmbedder(self._factory,
            lambda session:MemoryEmbeddingRepository(session,memory_repository(session))))
    def _retained_indexes(self):return self._generations.retained()
    def erase_items(self,identifiers):
        from app.runtime.received_results import result_journal
        values=tuple(identifiers);journal=result_journal('memory-embedding')
        for value in values:journal.close_item(value)
        for index in self._retained_indexes():index.erase_items(values)
    async def start(self):
        self._stopping=False;projection=None
        try:
            active,staging=self._generations.open()
            self._bind(active)
            if getattr(self,'validation_mode',False):
                self.status='ready'
                return
            projection=MemoryVectorProjection(self._factory,staging or active,
                on_clean_cycle=self._promote if staging else None,episode_only=self._episode_only,retained_indexes=self._retained_indexes)
            await projection.start()
            self.projection=projection;self.status='recovering' if staging else 'ready'
        except Exception:
            if projection is not None:await projection.stop()
            await self.canonical_worker.stop()
            self.status='vector_unavailable'
            raise
