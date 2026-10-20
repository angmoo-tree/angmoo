import asyncio
from types import SimpleNamespace
from app.runtime.memory.hybrid_runtime import MemoryHybridRuntime
from app.runtime.memory.hybrid_axes import VectorHybridAxis


def test_new_generation_waits_for_old_process_exit_and_stop_prevents_rebind():
    async def run(stopping):
        released = asyncio.Event()
        rebound = []
        class Workers:
            async def stop(self):
                await released.wait()
            def request_preparation(self):
                raise AssertionError("Old generation cannot prepare new work")
        runtime = object.__new__(MemoryHybridRuntime)
        runtime._stopping = False
        runtime._generations = SimpleNamespace(promote=lambda index: None)
        runtime.vector_axis = VectorHybridAxis(Workers(), None)
        runtime.fts = SimpleNamespace(_workers=SimpleNamespace(
            request_preparation=lambda: {"status": "ready", "reason": None}))
        runtime._bind = rebound.append
        runtime._promote("next-index")
        await asyncio.sleep(0)
        assert not rebound
        assert runtime.request_preparation()["vector"]["status"] == "preparing"
        runtime._stopping = stopping
        released.set()
        await runtime._transition
        assert rebound == ([] if stopping else ["next-index"])
    asyncio.run(run(False))
    asyncio.run(run(True))


def test_failed_axis_cleanup_does_not_skip_other_owned_workers():
    import pytest
    async def run():
        visited = []
        async def stop(name, fail=False):
            visited.append(name)
            if fail:
                raise RuntimeError("synthetic_cleanup_failed")
        runtime = object.__new__(MemoryHybridRuntime)
        runtime._transition = None
        runtime.fts = SimpleNamespace(_workers=SimpleNamespace(stop=lambda: stop("fts", True)))
        runtime.vector_axis = VectorHybridAxis(SimpleNamespace(stop=lambda: stop("vector")), None)
        runtime.canonical_worker = SimpleNamespace(stop=lambda: stop("canonical"))
        runtime.projection = SimpleNamespace(stop=lambda: stop("projection"))
        runtime._search_control = SimpleNamespace(close=lambda: visited.append("dispose"))
        with pytest.raises(ExceptionGroup, match="memory_runtime_cleanup_failed"):
            await runtime.stop()
        assert visited == ["fts", "vector", "canonical", "projection"]
        assert runtime.status == "cleanup_failed" and runtime._stopping
    asyncio.run(run())
