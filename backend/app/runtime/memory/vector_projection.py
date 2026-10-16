"""Incremental, restartable projection from accepted summary registrations."""
import asyncio
from time import time

from app.runtime.memory.recall_composition import recall_document_source


class MemoryVectorProjection:
    def __init__(self, session_factory, index, *, provider=None, on_clean_cycle=None, episode_only=False, retained_indexes=None):
        self._factory, self.index = session_factory, index
        self._source = recall_document_source(session_factory, episode_only=episode_only)
        self._retained_indexes = retained_indexes or (lambda: (self.index,))
        self._provider = provider
        from app.runtime.received_results import result_journal
        self.journal = result_journal("memory-embedding")
        self._received = {}
        self.last_usage = None
        self.generation = index.generation
        self._claims, self._boundaries = {}, {}
        self._attempt_keys = {}
        self._wake = asyncio.Event()
        self._wakeup = None
        self._task = None
        self._closing = False
        self.status = "stopped"
        self.last_code = None
        self.logical_calls = self.physical_attempts = 0
        # Physical-call budgets survive disposable projection generations.
        self._attempts_ready = False
        self._on_clean_cycle = on_clean_cycle
        self._tick_failed = False
        from app.runtime.memory.canonical_work import MemoryCanonicalWork
        self._canonical = MemoryCanonicalWork()

    def _prepare_attempts(self):
        from app.runtime.memory.vector_attempts import import_legacy
        import_legacy(self)

    def _claim_attempt(self, doc_id, profile, digest, credential_revision):
        return doc_id in self._claim_attempts(((doc_id, profile, digest, credential_revision),))

    def _claim_attempts(self, keys, *, prepared=()):
        from app.runtime.memory.vector_attempts import claim
        return claim(self, keys, time(), prepared=prepared)

    def _finish_attempt(self, doc_id, profile, digest, credential_revision, *, terminal):
        from app.runtime.memory.vector_attempts import finish
        finish(self, doc_id, profile, digest, credential_revision, terminal)

    async def sync_item(self, item_id, *, credential_revision=None):
        result = await self.sync_items((item_id,), credential_revision=credential_revision)
        return result[item_id]

    async def sync_items(self, item_ids, *, credential_revision=None):
        from app.runtime.memory.vector_batches import sync_items
        return await sync_items(self, item_ids, credential_revision=credential_revision)

    async def tick(self):
        from app.runtime.memory.vector_queue_worker import tick
        return await tick(self)

    async def _prepare_page(self):
        from app.runtime.memory.vector_preparation import prepare_page
        await prepare_page(self)

    async def start(self):
        self._closing = False
        if self._canonical.closed:
            from app.runtime.memory.canonical_work import MemoryCanonicalWork
            self._canonical = MemoryCanonicalWork()
        self.index.open()
        # Complete the legacy-budget handoff before bootstrap creates its
        # durable generation marker or any physical provider call is admitted.
        await self._canonical.call(self._prepare_attempts)
        if self._wakeup is None:
            from app.runtime.memory.vector_wakeup import VectorWakeup
            self._wakeup = VectorWakeup(self, asyncio.get_running_loop())
        self.status = "recovering"
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            try:
                self._wake.clear()
                more = await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.status, self.last_code = "degraded", "memory_vector_projection_failed"
                more = False
            if more:
                await asyncio.sleep(0)
                continue
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=5)
            except TimeoutError:
                pass

    def fence(self):
        self._closing = True
        if self._task is not None:
            self._task.cancel()

    async def stop(self):
        self.fence()
        if self._wakeup is not None:
            self._wakeup.close()
            self._wakeup = None
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.status = "stopped"
        await self._canonical.drain()
        self._canonical.close()
