"""Track only live HTTP stream tasks; canonical data still owns admission.

World erasure uses this neutral lifetime signal after its intent commits. No
provider result, user text or authority is stored in this process-local map.
"""
import asyncio
from threading import Lock


class WorldScopeStreams:
    def __init__(self):
        self._lock = Lock()
        self._streams = {}

    async def track(self, world_id, events):
        task, loop = asyncio.current_task(), asyncio.get_running_loop()
        entry = (loop, task)
        with self._lock:
            self._streams.setdefault(world_id, set()).add(entry)
        try:
            async for event in events:
                yield event
        finally:
            with self._lock:
                pending = self._streams.get(world_id, set())
                pending.discard(entry)
                if not pending:
                    self._streams.pop(world_id, None)
            await events.aclose()

    def close_world(self, world_id):
        with self._lock:
            entries = tuple(self._streams.get(world_id, ()))
        for loop, task in entries:
            if task and not task.done() and not loop.is_closed():
                loop.call_soon_threadsafe(task.cancel)
