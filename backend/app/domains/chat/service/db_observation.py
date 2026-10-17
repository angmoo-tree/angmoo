"""Attach existing opt-in capture to a request, including pre-ID admission."""
from contextlib import contextmanager, ExitStack
from functools import wraps
from app.core.work_observation import local_observer, scope
from app.core.session_write_observation import observe_session
from app.domains.chat.contracts.db_write_diagnostics import DbWriteCollector
from app.domains.chat.service.diagnostic_capture import capture


@contextmanager
def _binding(db, identity, generation, collector, stage):
    stack = ExitStack()
    try:
        stack.enter_context(local_observer(collector.observe, lambda: capture.generation_active(identity, generation)))
        stack.enter_context(scope(chat_stage=stage))
        stack.enter_context(observe_session(db))
    except Exception:
        try:
            stack.close()
        except Exception:
            pass
    try:
        yield
    finally:
        try:
            stack.close()
        except Exception:
            pass


def observe_admission(function):
    @wraps(function)
    def wrapped(self, db, user, world_id, thread_id, data):
        identity = (user.id, world_id, thread_id)
        try:
            generation = capture.generation(identity)
            collector = DbWriteCollector() if generation is not None else None
        except Exception:
            generation = None
        if generation is None:
            return function(self, db, user, world_id, thread_id, data)
        with _binding(db, identity, generation, collector, "admission"):
            result = function(self, db, user, world_id, thread_id, data)
        if result.outcome == "accepted":
            try:
                capture.bind_db(identity, result.response_request.request_id, generation, collector,
                    result.response_request.attempt_number)
            except Exception:
                pass
        return result
    return wrapped


def observe_generation(function):
    @wraps(function)
    async def wrapped(self, db, user, world_id, thread_id, request_id, **kwargs):
        identity = (user.id, world_id, thread_id)
        try:
            owned = capture.db_collector(identity, request_id)
        except Exception:
            owned = None
        if owned is None:
            async for event in function(self, db, user, world_id, thread_id, request_id, **kwargs):
                yield event
            return
        generation, collector = owned
        with _binding(db, identity, generation, collector, "workflow_checkpoint"):
            async for event in function(self, db, user, world_id, thread_id, request_id, **kwargs):
                yield event
    return wrapped
