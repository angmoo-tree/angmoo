"""Bounded SQL readers; PostgreSQL owns the cancellable search process."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from app.runtime.memory.postgresql_vector import PostgresSearchCancellation
from app.domains.memory.contracts.fts_recall import FtsWorkerRequest
from app.domains.memory.contracts.recall import MemoryRecallLexicalPolicy,MemoryRecallPreparing
from app.domains.memory.contracts.hybrid_recall import HybridAxisResult,RankedMemoryCandidate,RecallAxisReceipt,RecallAxisStatus
from app.contracts.retrieval_observation import Observation,current
from app.contracts.search_diagnostics import execution_collector,SearchTerminal
from app.runtime.memory.worker_diagnostics import WorkerTrace,current_worker,failure


class PostgresReadWorkers:
    def __init__(self,index,*,axis):
        if axis not in {'fts','vector'}:raise ValueError('postgresql_search_axis_invalid')
        self.index,self.axis=index,axis
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='pg-'+axis)
        self.slots=asyncio.Semaphore(2);self.pending=0;self.jobs={};self.stopped=False
    @property
    def active_processes(self):return set()
    @property
    def busy_jobs(self):return len(self.jobs)
    def preparation_status(self):
        if self.stopped:return {'status':'unavailable','reason':'memory_search_stopped'}
        try:
            if self.axis=='fts' and self.index.load_progress() is not None:
                return {'status':'preparing','reason':'memory_recall_projection_preparing'}
        except Exception:return {'status':'unavailable','reason':'postgresql_search_preparation_unavailable'}
        return {'status':'ready','reason':None}
    def request_preparation(self):return self.preparation_status()
    def _traced_execute(self,query,token,trace):
        context=current_worker.set(trace)
        try:
            with trace.phase('nn_query' if self.axis=='vector' else 'fts_search'):
                return self._execute(query,token)
        finally:current_worker.reset(context)
    def _execute(self,query,token):
        if token.expired():raise TimeoutError('postgresql_search_deadline')
        if self.axis=='vector':return self.index.search(query,cancellation=token)
        request=query if isinstance(query,FtsWorkerRequest) else FtsWorkerRequest(query)
        observation=Observation(detailed=request.capture_details);context=current.set(observation)
        started=monotonic();q=request.query
        try:
            try:
                batch=self.index.search_grouped(q,deadline=token.deadline,cancellation=token) if q.lexical_policy==MemoryRecallLexicalPolicy.GROUP_OR_V1 else None
                candidates=batch.candidates if batch is not None else self.index.search(q,deadline=token.deadline,cancellation=token)
                ranked=tuple(RankedMemoryCandidate(row,int(row.metadata['item_version']),row.metadata['document_content_hash']) for row in candidates[:q.limit])
                result=HybridAxisResult(ranked,RecallAxisReceipt('fts',batch.status if batch is not None else RecallAxisStatus.READY,
                    batch.executed if batch is not None else True,len(ranked),(monotonic()-started)*1000,batch.reason_code if batch is not None else None))
            except MemoryRecallPreparing:
                result=HybridAxisResult((),RecallAxisReceipt('fts',RecallAxisStatus.UNAVAILABLE,False,0,(monotonic()-started)*1000,'memory_recall_projection_preparing'))
            payload=observation.payload()
            if request.capture_details:payload.update(details=observation.details,detail_omitted=observation.detail_omitted)
            return result,payload
        finally:current.reset(context)
    async def search(self,query,*,deadline):
        target=execution_collector();trace=WorkerTrace(self.axis,deadline,domain='parent',detailed=target is not None)
        child=WorkerTrace(self.axis,deadline,detailed=target is not None)
        token=PostgresSearchCancellation(deadline);future=None;acquired=False;counted=False
        state='error';reason='abnormal_exit';received=False;cancelled=False
        try:
            if self.stopped or self.pending>=8:raise RuntimeError('postgresql_search_queue_unavailable')
            self.pending+=1;counted=True
            async with asyncio.timeout(max(0,deadline-monotonic())):
                with trace.phase('slot_wait'):await self.slots.acquire();acquired=True
                if self.stopped:raise RuntimeError('postgresql_search_stopped')
                future=asyncio.get_running_loop().run_in_executor(self.executor,self._traced_execute,query,token,child)
                self.jobs[future]=token
                result=await asyncio.shield(future);received=True;state='success';reason='none'
                return result
        except BaseException as exc:
            trace.error=child.error or failure(exc,child.last_stage or trace.last_stage)
            if isinstance(exc,asyncio.CancelledError):state='cancelled';reason='caller_cancel'
            elif isinstance(exc,TimeoutError):state='deadline';reason='deadline'
            raise
        finally:
            if future is not None:
                token.cancel()
                # Retain both admission and connection ownership through repeated
                # cancellation. Never admit a replacement while old SQL is alive.
                drain=asyncio.gather(future,return_exceptions=True)
                with trace.phase('worker_cleanup'):
                    while not drain.done():
                        try:await asyncio.shield(drain)
                        except asyncio.CancelledError:cancelled=True;token.cancel()
                self.jobs.pop(future,None)
            if acquired:self.slots.release()
            if counted:self.pending-=1
            if target is not None:
                for row in (*trace.stages.values(),*child.stages.values()):target.add_stage(row)
                target.terminals[self.axis]=SearchTerminal(axis=self.axis,terminal_state=state,
                    failure=trace.error or child.error,last_observed_stage=child.last_stage or trace.last_stage,
                    cause_certainty='reported',worker_started=future is not None,result_received=received,
                    terminal_observed=True,nn_query_started=child.metadata.get('nn_query_started') if self.axis=='vector' else None,
                    request_cleanup_complete=True,worker_state_after='retired' if self.stopped else 'ready',termination_reason=reason)
            if cancelled:raise asyncio.CancelledError
    async def stop(self):
        self.stopped=True
        for token in tuple(self.jobs.values()):token.cancel()
        if self.jobs:await asyncio.gather(*tuple(self.jobs),return_exceptions=True)
        self.executor.shutdown(wait=True,cancel_futures=False)
