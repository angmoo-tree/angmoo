"""Spawn entry: announce BOOT before importing either native search implementation."""
from time import monotonic

PROTOCOL = "memory-search-worker.v2"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024


class ResultSink:
    """The search target owns its connection; send only after its finally returns."""

    def __init__(self, pipe):
        self.pipe = pipe
        self.value = None
        self.closed = False

    def send(self, value):
        if self.value is not None:
            raise ValueError("memory_search_duplicate_result")
        self.value = value

    def close(self):
        self.closed = True


def run_worker(pipe, axis, worker_id, generation, arguments, progress, test_target=None):
    # No query/domain instance crosses spawn. The request is decoded after READY.
    import pickle

    def send(kind, **values):
        payload = pickle.dumps(dict(protocol=PROTOCOL, kind=kind, worker_id=worker_id,
                                    generation=generation, **values))
        if len(payload) > MAX_MESSAGE_BYTES:
            raise ValueError("memory_search_message_too_large")
        pipe.send_bytes(payload)

    try:
        send("BOOT")
        started = monotonic()
        if test_target is not None:
            target = test_target
        elif axis == "fts":
            from app.runtime.memory.fts_search_child import search as target
        elif axis == "vector":
            from app.runtime.memory.vector_search_child import search as target
        else:
            raise ValueError("memory_search_axis_invalid")
        from app.runtime.memory.worker_diagnostics import WorkerTrace, current_worker, capture_failure
        from app.contracts.retrieval_observation import current
        config = pickle.loads(arguments) if isinstance(arguments, bytes) else arguments
        send("READY", import_ms=(monotonic() - started) * 1000)
        while True:
            command = pickle.loads(pipe.recv_bytes(MAX_MESSAGE_BYTES))
            if (command.get("protocol"), command.get("worker_id"), command.get("generation")) != (
                    PROTOCOL, worker_id, generation):
                raise ValueError("memory_search_binding_mismatch")
            if command.get("kind") == "STOP":
                return
            if command.get("kind") != "RUN":
                raise ValueError("memory_search_command_invalid")
            job_id = command["job_id"]
            deadline = command["deadline"]
            trace = WorkerTrace(axis, deadline, progress=progress if command["capture"] else None,
                                detailed=command["capture"])
            trace_token = current_worker.set(trace)
            observation_token = current.set(None)
            sink = ResultSink(pipe)
            try:
                if deadline <= monotonic():
                    raise TimeoutError("memory_search_deadline")
                with trace.phase("child_bootstrap"):
                    pass
                target(sink, *config, command["query"], deadline)
            except BaseException as exc:
                capture_failure(exc)
                sink.value = (False, None)
            finally:
                current.reset(observation_token)
                current_worker.reset(trace_token)
            success, result = sink.value if sink.value is not None else (False, None)
            send("RESULT", job_id=job_id, success=success, result=result,
                 diagnostic=trace.snapshot())
            # Built-in targets return only after finally closes request resources.
            send("REQUEST_CLEANED", job_id=job_id)
            del command, sink, trace, result
            if not success:
                return  # Unknown native/IPC state must never be reused.
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        pipe.close()
