"""Two native hybrid reads plus a synthetic projection writer; no model calls.

Run with the evaluation-only dependency: uv run --with psutil python scripts/benchmark_grouped_fts_mixed.py --help
"""
import argparse
import asyncio
from datetime import UTC,datetime
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import threading
from time import monotonic,sleep
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.domains.memory.contracts.recall import MemoryRecallDocument,MemoryRecallSearchQuery,MemoryRecallLexicalPolicy,RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorQuery
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex,_prepare_document


async def measure(args):
    scope=MemoryScope('benchmark-owner','benchmark-world','benchmark-subject')
    fts=FtsReadWorkers(database_path=args.fts_db)
    vec=VectorReadWorkers(database_path=args.vector_db,extension_path=args.extension,
        extension_sha256=hashlib.sha256(args.extension.read_bytes()).hexdigest())
    rng=random.Random(20260914)
    vq=MemoryVectorQuery(scope,'benchmark-768-cos',tuple(rng.uniform(-1,1) for _ in range(768)))
    # Only this explicitly supplied synthetic FTS fixture is writable.
    writer=SqliteMemoryRecallIndex.reader(args.fts_db)
    writer._read_only=False
    with writer._connect(args.fts_db) as c:
        owners={r[0] for r in c.execute('SELECT DISTINCT owner_id FROM memory_recall_documents')}
        if not owners or owners-{'benchmark-owner','foreign-owner'}:
            raise ValueError('synthetic_scope_required')
        c.execute('PRAGMA journal_mode=WAL')
    output=[]
    for policy in MemoryRecallLexicalPolicy:
        q=MemoryRecallSearchQuery(scope,'별빛 축제 언제였지',(RecallDocumentKind.MEMORY_ITEM,),50,lexical_policy=policy)
        durations=[];fts_times=[];receipts=[];write_times=[]
        peaks={'tree':0,'fts_worker':0,'vector_worker':0};stop=threading.Event()
        def sample():
            parent=psutil.Process()
            while not stop.wait(.025):
                total=0
                for p in [parent]+parent.children(recursive=True):
                    try:
                        rss=p.memory_info().rss;total+=rss
                        if p.pid in fts.active_processes:peaks['fts_worker']=max(peaks['fts_worker'],rss)
                        if p.pid in vec.active_processes:peaks['vector_worker']=max(peaks['vector_worker'],rss)
                    except psutil.Error:pass
                peaks['tree']=max(peaks['tree'],total)
        monitor=threading.Thread(target=sample,daemon=True);monitor.start()
        async def pair():
            started=monotonic()
            async def lexical():
                result,_=await fts.search(q,deadline=monotonic()+15)
                fts_times.append((monotonic()-started)*1000)
                assert all(not c.candidate.document_id.startswith('foreign:') for c in result.candidates)
                receipts.append(result.receipt.status.value)
            await asyncio.gather(lexical(),vec.search(vq,deadline=monotonic()+15))
            durations.append((monotonic()-started)*1000)
        def write(n):
            start=monotonic()
            with writer._connect(args.fts_db) as c:
                c.execute('BEGIN IMMEDIATE')
                for j in range(3):
                    doc=MemoryRecallDocument(f'foreign:{policy.value}:{n}:{j}',f'foreign:{n}:{j}','foreign-owner',scope.world_id,
                        scope.subject_world_character_id,RecallDocumentKind.MEMORY_ITEM,'foreign','별빛 축제',
                        occurred_at=datetime.now(UTC),metadata={'item_version':'1'})
                    writer._insert_document(c,_prepare_document(doc))
                c.commit()
            write_times.append((monotonic()-start)*1000)
        try:
            for n in range(args.pairs):
                await asyncio.gather(pair(),pair(),asyncio.to_thread(write,n))
                if n%10==0:print(json.dumps({'policy':policy.value,'completed_reads':len(durations)}),flush=True)
        finally:
            stop.set();monitor.join()
        assert not fts.active_processes and not vec.active_processes
        def stats(values):
            values=sorted(values)
            return {'p50_ms':statistics.median(values),'p95_ms':values[min(len(values)-1,int(len(values)*.95))],'max_ms':max(values)}
        output.append({'policy':policy.value,'reads':len(durations),'hybrid_native':stats(durations),'fts_worker':stats(fts_times),
            'writer':stats(write_times),'peak_rss_bytes':peaks,'statuses':{x:receipts.count(x) for x in set(receipts)},'cross_scope_hits':0,'remaining_workers':0})
    # Keep the disposable fixture internally consistent after timed insertions.
    # This full projection digest refresh is intentionally outside writer timing.
    with writer._connect(args.fts_db) as connection:
        writer._refresh_state(connection)
    args.out.write_text(json.dumps({'results':output,'ai_calls':0,'scope':'synthetic','sampling_interval_seconds':.025,
        'limitations':['RSS sampled; OS cache warm','canonical/CRG excluded from native timing','synthetic vector values measure execution, not semantics',
            'writer measures SQLite projection row insertion, not canonical acceptance or projection digest refresh']},indent=2),encoding='utf-8')
    print(json.dumps(output),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('fts-db','vector-db','extension','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--wait-for',type=Path)
    p.add_argument('--pairs',type=int,default=50)
    args=p.parse_args()
    if args.wait_for:
        end=monotonic()+2400
        while not args.wait_for.exists():
            if monotonic()>=end:raise TimeoutError('prior_benchmark_not_finished')
            sleep(1)
    asyncio.run(measure(args))


if __name__=='__main__':main()
