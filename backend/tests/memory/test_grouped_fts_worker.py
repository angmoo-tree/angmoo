import asyncio
import pytest
from time import monotonic
from app.contracts.retrieval_observation import Observation,current
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.hybrid_axes import FtsHybridAxis
from memory.test_korean_memory_recall_quality import SCOPE, document, build_index


def test_spawn_policy_and_request_local_detail(tmp_path):
    index=build_index(tmp_path,[document('a','별빛 축제',metadata={'item_version':'1'})])
    workers=FtsReadWorkers(database_path=index.database_path)
    axis=FtsHybridAxis(workers,lexical_policy='group_or_v1')
    request=HybridRecallRequest('request','call','a'*64,SCOPE,'별빛 축제 언제','profile',(RecallDocumentKind.MEMORY_ITEM,))
    async def run(capture):
        observation=Observation(detailed=capture)
        token=current.set(observation)
        try:
            result=await axis.search(request,deadline=monotonic()+10)
            assert result.candidates and result.receipt.status.value=='ready'
            assert bool(observation.details) is capture
            assert any(e.get('policy')=='group_or_v1' for e in observation.events)
        finally: current.reset(token)
    async def main(): await asyncio.gather(run(True),run(False))
    asyncio.run(main())
    assert not workers.active_processes


def test_clipped_match_diagnostic_is_marked_incomplete():
    from app.contracts.retrieval_observation import detail
    observation=Observation(detailed=True,trace_active=True)
    token=current.set(observation)
    try:
        detail(match_query='a'*1600)
        assert len(observation.details[0]['match_query'])==1500
        assert observation.detail_omitted==1
        assert observation.payload()['events'][-1]['trace_complete'] is False
    finally:
        current.reset(token)


def test_cancel_queued_and_spawned_group_reads_releases_shared_slots(tmp_path):
    from app.domains.memory.contracts.recall import MemoryRecallSearchQuery
    workers=FtsReadWorkers(database_path=tmp_path/'unused.sqlite3',concurrency=1)
    query=MemoryRecallSearchQuery(SCOPE,'별빛 축제',(RecallDocumentKind.MEMORY_ITEM,),50,
        lexical_policy='group_or_v1')
    async def run():
        await workers._slots.acquire()
        queued=asyncio.create_task(workers.search(query,deadline=monotonic()+5))
        await asyncio.sleep(.01)
        assert not workers.active_processes
        queued.cancel()
        with pytest.raises(asyncio.CancelledError): await queued
        workers._slots.release()
        spawned=asyncio.create_task(workers.search(query,deadline=monotonic()+5))
        async with asyncio.timeout(2):
            while not workers.active_processes:
                await asyncio.sleep(0)
        spawned.cancel()
        with pytest.raises(asyncio.CancelledError): await spawned
        assert not workers.active_processes
        async with asyncio.timeout(.1): await workers._slots.acquire()
        workers._slots.release()
    asyncio.run(run())
