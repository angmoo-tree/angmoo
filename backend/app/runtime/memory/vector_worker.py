"""Bound native read processes; progress reporting never waits for a reader."""
import asyncio
import multiprocessing
from time import monotonic

from app.contracts.retrieval_observation import observe, current
from app.contracts.search_diagnostics import collector, SearchFailure, SearchStage, SearchTerminal
from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError, SqliteMemoryVectorIndex, VectorCancellation
from app.runtime.memory.worker_diagnostics import WorkerTrace, ProgressSlots, current_worker, phase, capture_failure, failure


def _search_child(pipe, database_path, extension_path, extension_sha256, generation, query, deadline):
    try:
        trace = current_worker.get()
        if trace is not None:
            trace.metadata.update(requested_generation=generation, requested_profile=query.profile)
        with phase("extension_verify"):
            index = SqliteMemoryVectorIndex(database_path, extension_path=extension_path,
                extension_sha256=extension_sha256, generation=generation)
        result = index.search(query, cancellation=VectorCancellation(deadline))
        pipe.send((True, result))
    except BaseException as exc:
        capture_failure(exc)
        pipe.send((False, "memory_vector_worker_failed"))
    finally:
        pipe.close()


class _DiagnosticPipe:
    def __init__(self, pipe, trace):
        self.pipe, self.trace = pipe, trace

    def send(self, value):
        with self.trace.phase("result_transport"):
            self.pipe.send({"protocol": "search-worker.v1", "success": value[0],
                "result": value[1] if value[0] else None, "diagnostic": self.trace.snapshot()})

    def close(self):
        self.pipe.close()


def _run_child(target, pipe, arguments, query, deadline, progress, detailed, axis):
    trace = WorkerTrace(axis, deadline, progress=progress, detailed=detailed)
    token = current_worker.set(trace)
    wrapped = _DiagnosticPipe(pipe, trace)
    try:
        with trace.phase("child_bootstrap"):
            pass
        target(wrapped, *arguments, query, deadline)
    except BaseException as exc:
        capture_failure(exc)
        try:
            wrapped.send((False, None))
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()
        current_worker.reset(token)


class VectorReadWorkers:
    _child_target = staticmethod(_search_child)
    _axis = "vector"

    def __init__(self, *, database_path, extension_path, extension_sha256,
                 generation="v1", concurrency=2):
        if not 1 <= concurrency <= 4:
            raise ValueError("memory_vector_worker_limit_invalid")
        self._slots = asyncio.Semaphore(concurrency)
        self._arguments = (database_path, extension_path, extension_sha256, generation)
        self._requested_generation = generation
        self.active_processes = set()

    async def search(self, query, *, deadline):
        target = collector()
        trace = WorkerTrace(self._axis, deadline, domain="parent", detailed=target is not None)
        if current.get() is not None:
            trace.started = current.get().started
        process = receiver = sender = progress = None
        cursor = 0
        child = {}
        progress_metadata = {}
        acquired = result_received = worker_started = terminate_sent = kill_sent = joined = False
        exit_code = None
        terminal_state, certainty, termination = "error", "unknown", "none"
        last_child = None
        cleanup_error = None

        def drain():
            nonlocal cursor, last_child
            if progress is None:
                return
            try:
                rows, cursor, metadata = progress.read(cursor)
                if metadata is not None:
                    progress_metadata.update(metadata)
                for row in rows:
                    last_child = row.stage
                    if target is not None:
                        target.add_stage(row)
            except Exception:
                trace.dropped += 1

        try:
            remaining = deadline-monotonic()
            if remaining <= 0:
                raise TimeoutError("memory_vector_deadline")
            async with asyncio.timeout(remaining):
                with trace.phase("slot_wait"):
                    await self._slots.acquire()
                    acquired = True
                context = multiprocessing.get_context("spawn")
                if target is not None:
                    progress = ProgressSlots(context)
                receiver, sender = context.Pipe(duplex=False)
                process = context.Process(target=_run_child,
                    args=(self._child_target, sender, self._arguments, query, deadline,
                        progress, target is not None, self._axis), daemon=True)
                with trace.phase("process_start"):
                    process.start()
                    worker_started = True
                    self.active_processes.add(process.pid)
                sender.close()
                with trace.phase("result_transport"):
                    while not receiver.poll():
                        drain()
                        if not process.is_alive():
                            raise MemoryVectorProjectionError("memory_vector_worker_exited")
                        await asyncio.sleep(0.005)
                    envelope = receiver.recv()
                    if not isinstance(envelope, dict) or envelope.get("protocol") != "search-worker.v1":
                        trace.error = SearchFailure(failure_code="result_decode_failed", failure_stage="result_transport")
                        raise MemoryVectorProjectionError("memory_vector_worker_protocol")
                    child = envelope["diagnostic"]
                    result_received = True
                    if not envelope["success"]:
                        if child.get("failure"):
                            trace.error = SearchFailure.model_validate(child["failure"])
                        raise MemoryVectorProjectionError("memory_vector_worker_failed")
                terminal_state, certainty = "success", "reported"
                return envelope["result"]
        except asyncio.CancelledError:
            terminal_state, certainty, termination = "cancelled", "last_stage_only", "caller_cancel"
            raise
        except TimeoutError as exc:
            terminal_state, certainty, termination = "deadline", "deadline_observed", "deadline"
            trace.error = failure(exc, trace.last_stage)
            raise
        except Exception as exc:
            if trace.error is None:
                trace.error = failure(exc, trace.last_stage)
            if trace.error.failure_code in {"worker_exited", "result_eof"}:
                terminal_state, certainty, termination = "unexpected_exit", "observed_exit", "abnormal_exit"
            elif result_received:
                certainty = "reported"
            raise
        finally:
            drain()
            try:
                with trace.phase("worker_cleanup"):
                    if process is not None and process.pid is not None:
                        if process.is_alive():
                            if termination == "none":
                                termination = "result_received_cleanup" if result_received else "abnormal_exit"
                            process.terminate()
                            terminate_sent = True
                        process.join(timeout=1.0)
                        if process.is_alive():
                            process.kill()
                            kill_sent = True
                            process.join(timeout=1.0)
                        exit_code = process.exitcode
                        joined = not process.is_alive()
                        self.active_processes.discard(process.pid)
                        process.close()
            except Exception:
                cleanup_error = "cleanup_failed"
            finally:
                if acquired:
                    self._slots.release()
                for connection in (receiver, sender):
                    if connection is not None:
                        try:
                            connection.close()
                        except OSError:
                            pass
            try:
                for row in child.get("stages", []):
                    stage = SearchStage.model_validate(row)
                    if target is not None:
                        target.add_stage(stage)
                    last_child = stage.stage
                requested = {}
                if self._axis == "vector":
                    requested = {"requested_generation": getattr(self, "_requested_generation", None),
                        "requested_profile": getattr(query, "profile", None)}
                metadata = {**requested, **progress_metadata, **child.get("metadata", {})}
                nn_started = metadata.pop("nn_query_started", False if result_received else None)
                summary = SearchTerminal(axis=self._axis, terminal_state=terminal_state,
                    failure=trace.error if terminal_state != "success" else None,
                    last_observed_stage=last_child, cause_certainty=certainty,
                    worker_started=worker_started, result_received=result_received,
                    nn_query_started=nn_started,
                    terminal_observed=result_received, worker_exit_code=exit_code,
                    terminate_sent=terminate_sent, kill_sent=kill_sent, joined=joined,
                    termination_reason=termination, cleanup_error_code=cleanup_error,
                    stage_events_dropped=trace.dropped + child.get("dropped", 0), **metadata)
                if target is not None:
                    for stage in trace.stages.values():
                        target.add_stage(stage)
                    target.terminals[self._axis] = summary
                observe("search_worker", axis=self._axis, status=terminal_state,
                    failure_code=None if summary.failure is None else summary.failure.failure_code,
                    failure_stage=None if summary.failure is None else summary.failure.failure_stage,
                    worker_started=worker_started, result_received=result_received,
                    nn_query_started=summary.nn_query_started, joined=joined)
            except Exception:
                if target is not None:
                    target.stage_dropped += 1
