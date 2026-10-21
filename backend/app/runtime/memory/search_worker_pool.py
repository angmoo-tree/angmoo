"""Small application-owned pools with per-process cancellation and bounded admission."""
from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import multiprocessing
import logging
import pickle
from time import monotonic
from uuid import uuid4

from app.contracts.search_diagnostics import SearchStage, SearchTerminal
from app.contracts.retrieval_observation import observe
from app.runtime.memory.search_worker_child import MAX_MESSAGE_BYTES, PROTOCOL, run_worker
from app.runtime.memory.worker_diagnostics import WorkerTrace, failure
from app.runtime.memory.search_worker_progress import ProgressSlots
from app.runtime.memory.preparation_budget import PROCESS_PREPARATION_SECONDS, ROUND_PREPARATION_SECONDS

logger = logging.getLogger(__name__)


class SearchWorkerUnavailable(RuntimeError):
    pass


class SearchWorkerControl:
    """Shared FTS/vector startup budget; blocking operations never run on the loop."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memory-search-control")
        self.preparation_slots = asyncio.Semaphore(2)

    async def run(self, function, *args):
        future = asyncio.get_running_loop().run_in_executor(self.executor, function, *args)
        return await asyncio.shield(future)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=False)


@dataclass(eq=False)
class WorkerSlot:
    identifier: str = field(default_factory=lambda: uuid4().hex)
    state: str = "starting"
    process: object = None
    pipe: object = None
    progress: object = None
    start_task: asyncio.Task | None = None
    sender: object = None
    retire_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    late_retirement: asyncio.Task | None = None
    io_tasks: set = field(default_factory=set)
    jobs: int = 0
    job_id: str | None = None
    preparation_ms: float | None = None
    child_import_ms: float | None = None
    boot_ms: float | None = None
    joined: bool = False
    terminate_sent: bool = False
    kill_sent: bool = False
    exit_code: int | None = None


class SearchReadWorkers:
    _axis = ""
    _child_target = None  # Private synthetic fault injection; never accepted over HTTP.

    def __init__(self, *, arguments, generation="v1", concurrency=2, control=None):
        if not 1 <= concurrency <= 2:
            raise ValueError("memory_search_worker_limit_invalid")
        self._arguments = arguments
        self._requested_generation = generation
        self._concurrency = concurrency
        self._own_control = control is None
        self._control = control or SearchWorkerControl()
        self._workers: list[WorkerSlot] = []
        self._waiters = deque()
        self._changed = asyncio.Condition()
        self._round = None
        self._jobs = set()
        self._retirements = set()
        self._stopped = False
        self._failed_at = None
        self._reason = None
        self._preparation_failure = None

    @property
    def active_processes(self):
        return {slot.process.pid for slot in self._workers
                if not slot.joined and slot.process is not None and slot.process.pid is not None}

    @property
    def busy_jobs(self):
        return sum(slot.job_id is not None for slot in self._workers)

    def preparation_status(self):
        if self._stopped:
            return {"status": "unavailable", "reason": "memory_search_stopped"}
        if any(slot.state in {"ready", "busy"} for slot in self._workers):
            return {"status": "ready", "reason": None}
        if self._round is not None and not self._round.done():
            return {"status": "preparing", "reason": None}
        if self._reason is not None:
            return {"status": "unavailable", "reason": self._reason}
        return {"status": "not_started", "reason": None}

    def request_preparation(self):
        if self._stopped or (self._round is not None and not self._round.done()):
            return self.preparation_status()
        if self._failed_at is not None and monotonic() - self._failed_at < 30:
            return self.preparation_status()
        missing = self._concurrency - len(self._workers)
        if missing:
            slots = [WorkerSlot() for _ in range(missing)]
            self._workers.extend(slots)  # Starting and quarantined slots count.
            self._reason = None
            self._preparation_failure = None
            self._round = asyncio.create_task(self._prepare_round(slots))
        return self.preparation_status()

    async def _notify(self):
        async with self._changed:
            self._changed.notify_all()

    async def _io(self, slot, function, *args):
        task = asyncio.create_task(self._control.run(function, *args))
        slot.io_tasks.add(task)
        def completed(done):
            slot.io_tasks.discard(done)
            # A cancelled caller no longer awaits this shielded operation.
            # Consume a late peer-close error while retaining its ownership.
            if not done.cancelled():
                done.exception()
        task.add_done_callback(completed)
        return await asyncio.shield(task)

    async def _receive(self, slot, deadline):
        async with asyncio.timeout(max(0, deadline - monotonic())):
            while not slot.pipe.poll():
                if not slot.process.is_alive():
                    raise SearchWorkerUnavailable("memory_vector_worker_exited")
                await asyncio.sleep(.005)
            payload = await self._io(slot, slot.pipe.recv_bytes, MAX_MESSAGE_BYTES)
        message = pickle.loads(payload)
        if not isinstance(message, dict) or (
                message.get("protocol"), message.get("worker_id"), message.get("generation")) != (
                PROTOCOL, slot.identifier, self._requested_generation):
            raise ValueError("memory_search_binding_mismatch")
        return message

    async def _prepare_round(self, slots):
        started = monotonic()
        try:
            async with asyncio.timeout_at(started + ROUND_PREPARATION_SECONDS):
                await asyncio.gather(*(self._prepare(slot) for slot in slots))
        except asyncio.CancelledError:
            raise
        except Exception:
            self._reason, self._failed_at = "memory_search_preparation_failed", monotonic()
        finally:
            for slot in slots:
                if slot.state == "starting":
                    await self._retire(slot)
            await self._notify()
            logger.info("memory_worker_preparation_round axis=%s budget_seconds=%s elapsed_ms=%.2f ready=%s retired=%s",
                        self._axis, ROUND_PREPARATION_SECONDS, (monotonic() - started) * 1000,
                        sum(s.state in {"ready", "busy"} for s in slots), sum(s.joined for s in slots))

    async def _prepare(self, slot):
        sender = None
        queued = monotonic()
        phase, started, error_type, admitted = "slot_wait", None, None, None
        try:
            async with self._control.preparation_slots:
                admitted = monotonic()
                if self._stopped:
                    return
                context = multiprocessing.get_context("spawn")
                slot.progress = ProgressSlots(context)
                slot.pipe, sender = context.Pipe(duplex=True)
                slot.sender = sender
                # Serialize production settings so spawn's unpickling cannot
                # import the application before the lightweight BOOT message.
                arguments = (pickle.dumps(self._arguments) if self._child_target is None
                             else self._arguments)
                slot.process = context.Process(target=run_worker,
                    args=(sender, self._axis, slot.identifier, self._requested_generation,
                          arguments, slot.progress, self._child_target), daemon=True)
                started = monotonic()
                deadline = started + PROCESS_PREPARATION_SECONDS
                phase = "process_start"
                slot.start_task = asyncio.create_task(self._control.run(slot.process.start))
                async with asyncio.timeout_at(deadline):
                    await asyncio.shield(slot.start_task)
                    sender.close()
                    sender = None
                    slot.sender = None
                    phase = "waiting_boot"
                    boot = await self._receive(slot, deadline)
                    slot.boot_ms = (monotonic() - started) * 1000
                    phase = "waiting_ready"
                    ready = await self._receive(slot, deadline)
                    if boot.get("kind") != "BOOT" or ready.get("kind") != "READY":
                        raise SearchWorkerUnavailable("memory_search_preparation_protocol")
                slot.preparation_ms = (monotonic() - started) * 1000
                slot.child_import_ms = ready["import_ms"]
                slot.state = "ready"
                phase = "ready"
                await self._notify()
        except asyncio.CancelledError:
            error_type = "CancelledError"
            await self._retire(slot)
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            self._preparation_failure = failure(exc, "process_start" if not slot.process or slot.process.pid is None else "child_bootstrap")
            self._reason, self._failed_at = "memory_search_preparation_failed", monotonic()
            await self._retire(slot)
        finally:
            if sender is not None and (slot.start_task is None or slot.start_task.done()):
                sender.close()
                slot.sender = None
            log = logger.warning if error_type else logger.info
            log("memory_worker_preparation axis=%s worker=%s phase=%s budget_seconds=%s queue_ms=%.2f preparation_ms=%s boot_ms=%s child_import_ms=%s exit_code=%s joined=%s error_type=%s elapsed_ms=%.2f",
                        self._axis, slot.identifier, phase, PROCESS_PREPARATION_SECONDS,
                        ((admitted or monotonic()) - queued) * 1000, slot.preparation_ms, slot.boot_ms,
                        slot.child_import_ms, slot.exit_code, slot.joined, error_type, (monotonic() - queued) * 1000)

    async def _retire(self, slot):
        async with slot.retire_lock:
            await self._retire_locked(slot)

    async def _late_retire(self, slot):
        await asyncio.gather(slot.start_task, return_exceptions=True)
        await self._retire(slot)

    async def _retire_locked(self, slot):
        """Do not release capacity until actual OS exit and channel cleanup."""
        if slot.joined:
            return
        idle = slot.state == "ready" and slot.job_id is None
        slot.state = "retiring"
        try:
            if slot.start_task is not None and not slot.start_task.done():
                done, _ = await asyncio.wait({slot.start_task}, timeout=1)
                if not done:
                    slot.state = "quarantined"
                    self._reason = "memory_search_cleanup_failed"
                    if slot.late_retirement is None:
                        slot.late_retirement = asyncio.create_task(self._late_retire(slot))
                        self._retirements.add(slot.late_retirement)
                        slot.late_retirement.add_done_callback(self._retirements.discard)
                    return
            if slot.sender is not None:
                slot.sender.close()
                slot.sender = None
            process = slot.process
            if process is not None and process.pid is not None:
                if idle and process.is_alive():
                    try:
                        async with asyncio.timeout(.25):
                            await self._io(slot, slot.pipe.send_bytes, pickle.dumps(dict(
                                protocol=PROTOCOL, kind="STOP", worker_id=slot.identifier,
                                generation=self._requested_generation)))
                        await self._control.run(process.join, .25)
                    except (OSError, TimeoutError):
                        pass
                if process.is_alive():
                    process.terminate()
                    slot.terminate_sent = True
                await self._control.run(process.join, 1)
                if process.is_alive():
                    process.kill()
                    slot.kill_sent = True
                    await self._control.run(process.join, 1)
                slot.exit_code = process.exitcode
                if process.is_alive():
                    slot.state = "quarantined"
                    self._reason = "memory_search_cleanup_failed"
                    return
                # Terminating closes the peer and unblocks partial-frame reads.
                if slot.io_tasks:
                    await asyncio.wait(tuple(slot.io_tasks), timeout=1)
                if any(not task.done() for task in slot.io_tasks):
                    slot.state = "quarantined"
                    self._reason = "memory_search_cleanup_failed"
                    return
                # OS exit is already confirmed; a handle-close diagnostic cannot
                # turn a reaped process into an unknown live one.
                try:
                    process.close()
                except OSError:
                    self._reason = "memory_search_handle_cleanup_failed"
            if slot.pipe is not None:
                slot.pipe.close()
            slot.joined = True
            slot.state = "retired"
            if slot in self._workers:
                self._workers.remove(slot)
        except Exception:
            slot.state = "quarantined"
            self._reason = "memory_search_cleanup_failed"
        finally:
            await self._notify()

    async def _retire_owned(self, slot):
        task = asyncio.create_task(self._retire(slot))
        self._retirements.add(task)
        task.add_done_callback(self._retirements.discard)
        await asyncio.shield(task)

    async def _acquire(self, deadline):
        ticket = object()
        if self._stopped:
            raise SearchWorkerUnavailable("memory_search_stopped")
        if len(self._waiters) >= 8:
            raise SearchWorkerUnavailable("memory_search_queue_full")
        if monotonic() >= deadline:
            raise TimeoutError("memory_search_deadline")
        self._waiters.append(ticket)
        self.request_preparation()
        try:
            async with asyncio.timeout(max(0, deadline - monotonic())), self._changed:
                while True:
                    if self._stopped:
                        raise SearchWorkerUnavailable("memory_search_stopped")
                    slot = next((row for row in self._workers if row.state == "ready"), None)
                    if self._waiters[0] is ticket and slot is not None:
                        if monotonic() >= deadline:
                            raise TimeoutError("memory_search_deadline")
                        slot.state = "busy"
                        slot.job_id = uuid4().hex
                        return slot
                    if not any(row.state == "starting" for row in self._workers) and not self.busy_jobs and slot is None:
                        raise SearchWorkerUnavailable(self._reason or "memory_search_unavailable")
                    await self._changed.wait()
        finally:
            self._waiters.remove(ticket)
            await self._notify()

    async def search(self, query, *, deadline):
        from app.contracts.search_diagnostics import execution_collector
        target = execution_collector()
        trace = WorkerTrace(self._axis, deadline, domain="parent", detailed=target is not None)
        slot = None
        child = {}
        cursor = 0
        last_child = None
        metadata = {"requested_generation": self._requested_generation, "requested_profile": getattr(query, "profile", None)}
        result_received = cleaned = False
        terminal_state, termination = "error", "none"
        task = asyncio.current_task()
        self._jobs.add(task)

        def drain():
            nonlocal cursor, last_child
            if target is None or slot is None:
                return
            try:
                rows, cursor, values = slot.progress.read(cursor)
            except Exception:
                target.stage_dropped += 1
                return
            metadata.update(values or {})
            for row in rows:
                try:
                    target.add_stage(row)
                    last_child = row.stage
                except Exception:
                    target.stage_dropped += 1

        async def receive():
            # Keep partial progress available even when the child never returns.
            pending = asyncio.create_task(self._receive(slot, deadline))
            try:
                while not pending.done():
                    drain()
                    await asyncio.wait({pending}, timeout=.01)
                return await pending
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

        try:
            with trace.phase("waiting_ready"):
                slot = await self._acquire(deadline)
            slot.progress.reset()
            command = dict(protocol=PROTOCOL, kind="RUN", worker_id=slot.identifier,
                generation=self._requested_generation, job_id=slot.job_id,
                query=query, deadline=deadline, capture=target is not None)
            payload = pickle.dumps(command)
            if len(payload) > MAX_MESSAGE_BYTES:
                raise ValueError("memory_search_message_too_large")
            async with asyncio.timeout(max(0, deadline - monotonic())):
                await self._io(slot, slot.pipe.send_bytes, payload)
                with trace.phase("result_transport"):
                    envelope = await receive()
                    if envelope.get("kind") != "RESULT" or envelope.get("job_id") != slot.job_id:
                        raise SearchWorkerUnavailable("memory_search_result_mismatch")
                    child = envelope["diagnostic"]
                    result_received = True
                with trace.phase("request_cleanup"):
                    acknowledgement = await receive()
                    if acknowledgement.get("kind") != "REQUEST_CLEANED" or acknowledgement.get("job_id") != slot.job_id:
                        raise SearchWorkerUnavailable("memory_search_cleanup_mismatch")
                    cleaned = True
                if not envelope["success"]:
                    from app.contracts.search_diagnostics import SearchFailure
                    if child.get("failure"):
                        trace.error = SearchFailure.model_validate(child["failure"])
                    raise SearchWorkerUnavailable("memory_search_worker_failed")
                if monotonic() >= deadline:
                    raise TimeoutError("memory_search_deadline")
                terminal_state = "success"
                return envelope["result"]
        except asyncio.CancelledError:
            terminal_state, termination = "cancelled", "caller_cancel"
            raise
        except TimeoutError as exc:
            terminal_state, termination = "deadline", "deadline"
            trace.error = failure(exc, trace.last_stage)
            raise
        except Exception as exc:
            if slot is None and self._preparation_failure is not None:
                trace.error = self._preparation_failure
            elif trace.error is None:
                trace.error = failure(exc, trace.last_stage)
            if trace.error.failure_code in {"worker_exited", "result_eof"}:
                terminal_state, termination = "unexpected_exit", "abnormal_exit"
            raise
        finally:
            try:
                drain()
                if slot is not None and terminal_state != "success":
                    with trace.phase("worker_cleanup"):
                        await self._retire_owned(slot)
                if target is not None:
                    try:
                        for row in child.get("stages", []):
                            stage = SearchStage.model_validate(row)
                            target.add_stage(stage)
                            last_child = stage.stage
                        metadata.update(child.get("metadata", {}))
                        nn_started = metadata.pop("nn_query_started", False if result_received else None)
                        for stage in trace.stages.values():
                            target.add_stage(stage)
                        target.terminals[self._axis] = SearchTerminal(axis=self._axis,
                            terminal_state=terminal_state, failure=trace.error,
                            last_observed_stage=last_child,
                            cause_certainty="reported" if result_received else "last_stage_only",
                            worker_started=slot is not None, result_received=result_received,
                            terminal_observed=result_received, nn_query_started=nn_started,
                            joined=bool(slot and slot.joined), worker_exit_code=slot.exit_code if slot else None,
                            terminate_sent=bool(slot and slot.terminate_sent), kill_sent=bool(slot and slot.kill_sent),
                            termination_reason=termination, request_cleanup_complete=cleaned,
                            worker_state_after=("ready" if terminal_state == "success" else slot.state) if slot else "preparing",
                            worker_reused=bool(slot and slot.jobs), preparation_ms=slot.preparation_ms if slot else None,
                            boot_ms=slot.boot_ms if slot else None, child_import_ms=slot.child_import_ms if slot else None,
                            **metadata)
                    except Exception:
                        target.stage_dropped += 1
            finally:
                if slot is not None:
                    slot.job_id = None
                    if terminal_state == "success":
                        slot.jobs += 1
                        slot.state = "ready"
                self._jobs.discard(task)
                await self._notify()
            observe("search_worker", axis=self._axis, status=terminal_state,
                    worker_started=slot is not None, result_received=result_received,
                    joined=bool(slot and slot.joined))

    async def stop(self):
        self._stopped = True
        await self._notify()
        if self._round is not None and not self._round.done():
            self._round.cancel()
            await asyncio.gather(self._round, return_exceptions=True)
        jobs = tuple(self._jobs)
        for task in jobs:
            task.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        for slot in tuple(self._workers):
            await self._retire_owned(slot)
        if self._retirements:
            await asyncio.wait(tuple(self._retirements), timeout=3)
        if self._workers:
            raise SearchWorkerUnavailable("memory_search_cleanup_failed")
        if self._own_control:
            self._control.close()
