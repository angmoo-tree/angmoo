import asyncio,threading,time
import psycopg
from app.runtime.memory.postgresql_workers import PostgresReadWorkers
from app.runtime.memory.worker_diagnostics import failure
from app.contracts.search_diagnostics import SearchSummaryCollector,summary_current


def test_postgresql_failure_has_safe_sqlstate():
    result=failure(psycopg.errors.SerializationFailure('private SQL payload'),'nn_query')
    assert result.failure_code=='postgresql_serialization' and result.postgresql_sqlstate=='40001'
    assert 'private' not in result.model_dump_json()


def test_repeated_cancel_keeps_slot_until_query_drained_and_records_terminal():
    entered=threading.Event();release=threading.Event()
    class Index:
        def search(self,q,cancellation):
            entered.set();release.wait(3)
            return 'synthetic-result'
    async def exercise():
        workers=PostgresReadWorkers(Index(),axis='vector');collector=SearchSummaryCollector()
        token=summary_current.set(collector)
        try:
            job=asyncio.create_task(workers.search(None,deadline=time.monotonic()+5))
            while not entered.is_set():await asyncio.sleep(.005)
            job.cancel();await asyncio.sleep(.02);job.cancel();await asyncio.sleep(.02)
            assert workers.pending==1 and workers.busy_jobs==1 and workers.slots._value==1
            release.set()
            try:await job
            except asyncio.CancelledError:pass
            else:raise AssertionError('cancellation lost')
            assert workers.pending==0 and workers.busy_jobs==0 and workers.slots._value==2
            terminal=collector.terminals['vector']
            assert terminal.terminal_state=='cancelled' and terminal.request_cleanup_complete
            assert await workers.search(None,deadline=time.monotonic()+2)=='synthetic-result'
            assert collector.terminals['vector'].terminal_state=='success'
        finally:summary_current.reset(token);release.set();await workers.stop()
    asyncio.run(exercise())
