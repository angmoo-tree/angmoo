"""Spawn-safe shared progress storage; domain DTO parsing occurs only on read."""
import json


class ProgressSlots:
    """32 immutable packets. A killed writer can never block its reader.

    Unlike Queue/Pipe progress, there is no feeder or partial-frame receive.
    A nonblocking lock protects publication. Losing a packet loses diagnostics
    only; the terminal envelope carries the full available snapshot.
    """
    CAPACITY = 32
    WIDTH = 512

    def __init__(self, context):
        self.data = context.RawArray("B", self.CAPACITY * self.WIDTH)
        self.lengths = context.RawArray("i", self.CAPACITY)
        self.lock = context.Lock()
        self.metadata = context.RawArray("B", 1024)
        self.metadata_length = context.RawValue("i", 0)

    def write(self, value, metadata=None):
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode()
        if len(payload) > self.WIDTH or not self.lock.acquire(False):
            return False
        try:
            meta = json.dumps(metadata or {}, separators=(",", ":"), ensure_ascii=True).encode()
            if len(meta) <= 1024:
                self.metadata[:len(meta)] = meta
                self.metadata_length.value = len(meta)
            index = next((i for i, size in enumerate(self.lengths) if size == 0), None)
            if index is None:
                return False
            start = index*self.WIDTH
            self.data[start:start+len(payload)] = payload
            self.lengths[index] = len(payload)
            return True
        finally:
            self.lock.release()

    def reset(self):
        """Called only while the child is idle, before assigning its next job."""
        if not self.lock.acquire(False):
            raise RuntimeError("memory_search_progress_not_clean")
        try:
            for index in range(self.CAPACITY):
                self.lengths[index] = 0
            self.metadata_length.value = 0
        finally:
            self.lock.release()

    def read(self, after=0):
        from app.contracts.search_diagnostics import SearchStage
        if not self.lock.acquire(False):
            return [], after, None
        try:
            rows = []
            while after < self.CAPACITY and self.lengths[after]:
                size = self.lengths[after]
                if not 0 < size <= self.WIDTH:
                    break
                start = after*self.WIDTH
                rows.append(SearchStage.model_validate_json(bytes(self.data[start:start+size])))
                after += 1
            size = self.metadata_length.value
            meta = json.loads(bytes(self.metadata[:size])) if 0 < size <= 1024 else None
            return rows, after, meta
        finally:
            self.lock.release()
