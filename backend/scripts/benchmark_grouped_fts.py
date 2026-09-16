"""Synthetic native FTS benchmark; explicit output directory, no user DB or AI.

Run with the evaluation-only dependency: uv run --with psutil python scripts/benchmark_grouped_fts.py --help
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import gc
import json
from pathlib import Path
import statistics
import sys
from time import monotonic, process_time
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.domains.memory.contracts.recall import MemoryRecallDocument,MemoryRecallSearchQuery,MemoryRecallLexicalPolicy,RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, _prepare_document
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

SCOPE=MemoryScope('benchmark-owner','benchmark-world','benchmark-subject')


def percentiles(rows):
    values=sorted(rows)
    return {'p50_ms':statistics.median(values),'p95_ms':values[min(len(values)-1,int(len(values)*.95))],'max_ms':max(values)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--sizes',type=int,nargs='+',default=[10000,100000])
    parser.add_argument('--repeats',type=int,default=100)
    parser.add_argument('--workers-only',action='store_true')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    for size in args.sizes:
        path=args.out/str(size)
        index=SqliteMemoryRecallIndex(StaticRuntimeDataPath(path))
        if not index.database_path.exists():
            now=datetime(2026,9,14,tzinfo=UTC)
            def documents():
                for n in range(size):
                    for prefix in ('summary','evidence'):
                        yield MemoryRecallDocument(f'{prefix}:{n}',str(n),SCOPE.owner_id,SCOPE.world_id,SCOPE.subject_world_character_id,
                            RecallDocumentKind.MEMORY_ITEM,str(n),f'별빛 축제 공연 연습 기록 장소{n} 민아와 9월 13일 공연은 취소됐다.',
                            occurred_at=now,metadata={'item_version':'1'})
            began=monotonic()
            index.database_path.parent.mkdir(parents=True,exist_ok=True)
            # Fixture construction only: use identical schema/token writer but do
            # not measure promotion/doctor's whole-index verification as retrieval.
            index._build_database(index.database_path, (_prepare_document(d) for d in documents()))
            print(json.dumps({'built_memories':size,'documents':2*size,'seconds':monotonic()-began}),flush=True)
        reader=SqliteMemoryRecallIndex.reader(index.database_path)
        rows=[]
        for policy in MemoryRecallLexicalPolicy:
            for label,text in [('common','별빛 축제 언제였지'),('rare',f'장소{size-1}'),('empty','존재하지않는유니콘')]:
                if args.workers_only:
                    continue
                q=MemoryRecallSearchQuery(SCOPE,text,(RecallDocumentKind.MEMORY_ITEM,),50,lexical_policy=policy)
                times=[];statuses={};cpu=process_time();rss=psutil.Process().memory_info().rss
                for _ in range(args.repeats):
                    started=monotonic()
                    if policy==MemoryRecallLexicalPolicy.GROUP_OR_V1:
                        batch=reader.search_grouped(q,deadline=monotonic()+5)
                        status=batch.status.value
                    else:
                        result=reader.search(q);status='ready'
                    times.append((monotonic()-started)*1000)
                    statuses[status]=statuses.get(status,0)+1
                    rss=max(rss,psutil.Process().memory_info().rss)
                row={'memories':size,'documents':2*size,'policy':policy.value,'workload':label,'n':len(times),**percentiles(times),
                    'cpu_seconds':process_time()-cpu,'sampled_parent_rss_bytes':rss,'statuses':statuses}
                rows.append(row);print(json.dumps(row),flush=True)
                (args.out/f'{size}-warm-receipt.json').write_text(json.dumps({'rows':rows},indent=2),encoding='utf-8')
                gc.collect()
        async def workers_test():
            workers=FtsReadWorkers(database_path=index.database_path)
            output=[]
            for policy in MemoryRecallLexicalPolicy:
                q=MemoryRecallSearchQuery(SCOPE,'별빛 축제 언제였지',(RecallDocumentKind.MEMORY_ITEM,),50,lexical_policy=policy)
                times=[];statuses=[]
                for _ in range(5):
                    started=monotonic()
                    try:
                        result,_=await workers.search(q,deadline=monotonic()+5)
                        statuses.append(result.receipt.status.value)
                    except TimeoutError:
                        statuses.append('timeout')
                    times.append((monotonic()-started)*1000)
                output.append({'policy':policy.value,'new_process_os_cache_warm':True,'n':5,'statuses':statuses,**percentiles(times)})
            q=replace(q,text='별빛')
            job=asyncio.create_task(workers.search(q,deadline=monotonic()+5))
            await asyncio.sleep(.02);job.cancel()
            try:await job
            except asyncio.CancelledError:pass
            assert not workers.active_processes
            return output
        workers=asyncio.run(workers_test())
        (args.out/f'{size}-receipt.json').write_text(json.dumps({'rows':rows,'workers':workers,'ai_calls':0,
            'limitations':['Fixture built with production schema/token writer; promotion/doctor not benchmarked','OS cache not cleared','parent RSS is sampled, not total worker peak','concurrent vector/writer measured separately']},indent=2),encoding='utf-8')


if __name__=='__main__':main()
