"""Authorize a thread's optional search preparation without creating Chat work."""
import asyncio
from types import SimpleNamespace


class SearchPreparationService:
    def __init__(self, threads, session_factory, read_settings, prepare, *, enabled=True):
        self._threads = threads
        self._sessions = session_factory
        self._read_settings = read_settings
        self._prepare = prepare
        self._enabled = enabled

    def _authorized_settings(self, user, world_id, thread_id):
        with self._sessions() as db:
            actor_id = self._threads.search_preparation_subject(db, user, world_id, thread_id)
            return self._read_settings(db, user.id, world_id, actor_id)

    async def prepare(self, user, world_id, thread_id):
        principal = SimpleNamespace(id=user.id)
        enabled, semantic = await asyncio.to_thread(self._authorized_settings, principal, world_id, thread_id)
        # The read Session has ended before the Runtime schedules any preparation.
        axes = (self._prepare(semantic=semantic) if enabled and self._enabled and self._prepare is not None
                else {axis: {"status": "disabled", "reason": None} for axis in ("fts", "vector")})
        return {"schema_version": "memory-search-preparation.v1",
                "world_id": world_id, "thread_id": thread_id, "axes": axes}
