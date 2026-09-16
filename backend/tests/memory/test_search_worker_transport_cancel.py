"""Cancellation while the child prepares transport must release its read slot."""
import asyncio
import time
from time import monotonic

import pytest

from app.contracts.retrieval_observation import Observation, current
from app.contracts.search_diagnostics import collector
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.memory.worker_diagnostics import phase


def transport_child(pipe, mode, query, deadline):
    if mode == "wait":
        with phase("result_transport"):
            time.sleep(20)
    pipe.send((True, "finished"))


class TransportWorkers(VectorReadWorkers):
    _child_target = staticmethod(transport_child)

    def __init__(self):
        self._slots = asyncio.Semaphore(1)
        self._arguments = ("wait",)
        self.active_processes = set()


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_transport_stop_is_reaped_and_next_request_can_use_slot(stop):
    async def run():
        worker = TransportWorkers()
        observation = Observation(detailed=True)
        token = current.set(observation)
        try:
            task = asyncio.create_task(worker.search(None, deadline=monotonic()+6))
            try:
                async with asyncio.timeout(5):
                    while not any(s.clock_domain == "child" and s.stage == "result_transport"
                                  for s in collector().stages.values()):
                        await asyncio.sleep(.005)
                if stop == "cancel":
                    task.cancel()
                with pytest.raises(asyncio.CancelledError if stop == "cancel" else TimeoutError):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            terminal = collector().payload()["terminals"][0]
            assert terminal["joined"] and not terminal["result_received"]
            assert terminal["last_observed_stage"] == "result_transport"
            assert not worker.active_processes
            worker._arguments = ("ok",)
            assert await worker.search(None, deadline=monotonic()+6) == "finished"
            assert not worker.active_processes
        finally:
            current.reset(token)
    asyncio.run(run())
